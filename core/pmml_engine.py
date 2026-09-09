"""
core.pmml_engine
================
Motor de inferencia sobre modelos PMML.

Responsabilidades:
  * Leer el esquema de entrada declarado por el modelo.
  * Validar que el dataset cubre ese esquema ANTES de invocar a Java.
  * Puntuar por bloques, informando avance y liberando memoria.
  * Resolver colisiones de nombre entre variables de entrada y de salida.

La validacion previa es deliberada: sin ella, una columna faltante se
manifiesta como un `KeyError` de pandas o una excepcion Java ilegible, y el
analista no sabe que variable falta. Aqui el error dice exactamente que
columnas se esperaban y cuales llegaron.
"""

from __future__ import annotations

import gc
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional

import pandas as pd

from core.data_utils import ReporteCasteo, aplicar_esquema


class ErrorEsquemaPMML(Exception):
    """El dataset no satisface el esquema de entrada exigido por el modelo."""


@dataclass
class ResultadoScoring:
    """Salida completa de una corrida de scoring, con su traza de calidad."""

    datos: pd.DataFrame
    campos_entrada: List[str] = field(default_factory=list)
    campos_salida: List[str] = field(default_factory=list)
    reporte_casteo: Optional[ReporteCasteo] = None
    filas_procesadas: int = 0
    filas_con_error: int = 0
    filas_sin_score: int = 0
    resumen_segmentos: Optional[pd.DataFrame] = None


def contar_sin_score(df: pd.DataFrame, campos_salida: List[str]) -> int:
    """
    Cuenta los registros que no obtuvieron ningun valor de salida.

    Un PMML sin estrategia de imputacion devuelve nulo cuando falta un
    predictor obligatorio. Esos registros salen del proceso sin score y, si
    nadie los cuenta, se pierden en silencio: en una cartera eso significa
    solicitudes que ningun motor decidio. Por eso se reporta explicitamente.
    """
    presentes = [c for c in campos_salida if c in df.columns]
    if not presentes:
        return 0
    return int(df[presentes].isna().all(axis=1).sum())


def describir_campos(campos) -> pd.DataFrame:
    """Convierte los ModelField de JPMML en una tabla legible."""
    registros = []
    for campo in campos:
        registros.append(
            {
                "Variable": str(campo.getName()),
                "Tipo de dato": str(campo.getDataType()),
                "Tipo operativo": str(campo.getOpType()),
            }
        )
    return pd.DataFrame(registros)


def obtener_esquema_entrada(evaluador) -> Dict[str, str]:
    """
    Esquema {variable: tipo_pandas} derivado de los campos de entrada del PMML.

    En jpmml_evaluator 0.16 `ModelField.getDataType()` ya devuelve una cadena
    normalizada ('double', 'integer', 'string', ...), asi que no hace falta la
    introspeccion defensiva que tenia la version anterior.
    """
    from core.data_utils import MAPA_TIPOS_PMML  # import local: evita ciclo

    esquema: Dict[str, str] = {}
    for campo in evaluador.getInputFields():
        nombre = str(campo.getName())
        tipo_pmml = str(campo.getDataType()).strip()
        esquema[nombre] = MAPA_TIPOS_PMML.get(tipo_pmml, "string")
    return esquema


def nombres_entrada(evaluador) -> List[str]:
    """Orden exacto de las variables de entrada que espera el evaluador."""
    return [str(campo.getName()) for campo in evaluador.getInputFields()]


def validar_cobertura(df: pd.DataFrame, requeridas: List[str]) -> None:
    """Falla temprano y con un mensaje accionable si faltan variables."""
    faltantes = [c for c in requeridas if c not in df.columns]
    if not faltantes:
        return

    disponibles = list(df.columns)
    muestra = ", ".join(disponibles[:15]) + (" ..." if len(disponibles) > 15 else "")
    raise ErrorEsquemaPMML(
        f"El dataset no contiene {len(faltantes)} variable(s) que el modelo "
        f"requiere: {', '.join(faltantes)}.\n\n"
        f"Columnas presentes en el archivo ({len(disponibles)}): {muestra}\n\n"
        "Revisa que el archivo de datos corresponda a este modelo y que los "
        "nombres coincidan exactamente (mayúsculas y acentos incluidos)."
    )


def _desambiguar_salidas(
    df_entrada: pd.DataFrame, df_salida: pd.DataFrame
) -> pd.DataFrame:
    """
    Renombra las columnas de salida que chocan con columnas de entrada.

    Sin esto, `pd.concat` genera columnas duplicadas y cualquier seleccion
    posterior devuelve un DataFrame en lugar de una Serie, rompiendo el
    analisis aguas abajo.
    """
    colisiones = set(df_entrada.columns) & set(df_salida.columns)
    if not colisiones:
        return df_salida
    return df_salida.rename(columns={c: f"{c}_pmml" for c in colisiones})


def puntuar(
    evaluador,
    df: pd.DataFrame,
    tamano_bloque: int = 5_000,
    callback_progreso: Optional[Callable[[int, int], None]] = None,
) -> pd.DataFrame:
    """
    Evalua el modelo sobre el DataFrame completo procesando por bloques.

    El bloqueo cumple dos funciones: acota el pico de memoria al serializar
    hacia la JVM y permite reportar avance en corridas largas, que en carteras
    de credito pueden ser de cientos de miles de registros.
    """
    orden_entrada = nombres_entrada(evaluador)
    validar_cobertura(df, orden_entrada)

    total = len(df)
    if total == 0:
        return df.copy()

    tamano_bloque = max(int(tamano_bloque), 1)
    bloques: List[pd.DataFrame] = []

    for inicio in range(0, total, tamano_bloque):
        bloque = df.iloc[inicio : inicio + tamano_bloque]
        entrada = bloque[orden_entrada]

        predicciones = evaluador.evaluateAll(entrada)
        if isinstance(predicciones, pd.Series):
            predicciones = predicciones.to_frame(name="prediction")

        predicciones = predicciones.copy()
        predicciones.index = bloque.index
        predicciones = _desambiguar_salidas(bloque, predicciones)

        bloques.append(pd.concat([bloque, predicciones], axis=1))

        if callback_progreso is not None:
            callback_progreso(min(inicio + tamano_bloque, total), total)

        del bloque, entrada, predicciones
        gc.collect()

    return pd.concat(bloques, axis=0)


def ejecutar_modelo_unico(
    evaluador,
    df_crudo: pd.DataFrame,
    esquema_externo: Optional[Dict[str, str]] = None,
    tamano_bloque: int = 5_000,
    callback_progreso: Optional[Callable[[int, int], None]] = None,
) -> ResultadoScoring:
    """Flujo completo de scoring con un solo modelo: tipar, validar y puntuar."""
    esquema = esquema_externo or obtener_esquema_entrada(evaluador)

    df_tipado, reporte = aplicar_esquema(df_crudo, esquema)
    validar_cobertura(df_tipado, nombres_entrada(evaluador))

    df_puntuado = puntuar(
        evaluador, df_tipado, tamano_bloque=tamano_bloque, callback_progreso=callback_progreso
    )

    columnas_error = [c for c in df_puntuado.columns if c == "errors"]
    filas_con_error = 0
    if columnas_error:
        filas_con_error = int(df_puntuado["errors"].notna().sum())

    campos_salida = [str(c.getName()) for c in evaluador.getOutputFields()]

    return ResultadoScoring(
        datos=df_puntuado,
        campos_entrada=nombres_entrada(evaluador),
        campos_salida=campos_salida,
        reporte_casteo=reporte,
        filas_procesadas=len(df_puntuado),
        filas_con_error=filas_con_error,
        filas_sin_score=contar_sin_score(df_puntuado, campos_salida),
    )


def ejecutar_multimodelo(
    df_crudo: pd.DataFrame,
    variable_segmento: str,
    evaluadores_por_segmento: Dict[str, object],
    esquema_externo: Optional[Dict[str, str]] = None,
    tamano_bloque: int = 5_000,
    callback_progreso: Optional[Callable[[str, int, int], None]] = None,
) -> ResultadoScoring:
    """
    Enruta cada registro al modelo que corresponde a su segmento y consolida.

    Endurecimientos respecto de la version original:
      * Se valida que la variable de enrutamiento exista (antes: KeyError seco).
      * Los segmentos sin modelo asignado se reportan en vez de descartarse en
        silencio, que en un proceso de riesgo es un fallo grave e invisible.
      * Si ningun segmento cruza, se explica el motivo en lugar de fallar con
        "No objects to concatenate".
    """
    if variable_segmento not in df_crudo.columns:
        disponibles = ", ".join(list(df_crudo.columns)[:15])
        raise ErrorEsquemaPMML(
            f"La variable de enrutamiento '{variable_segmento}' no existe en el "
            f"dataset. Columnas disponibles: {disponibles} ..."
        )

    df_trabajo = df_crudo.copy()
    # Normalizacion del segmento: '1.0' y '1' deben resolver al mismo modelo.
    from core.data_utils import limpiar_llave_primaria  # import local

    df_trabajo[variable_segmento] = limpiar_llave_primaria(df_trabajo[variable_segmento])

    claves_modelo = {str(k).strip(): v for k, v in evaluadores_por_segmento.items()}
    presentes = [str(s) for s in df_trabajo[variable_segmento].dropna().unique()]
    con_modelo = [s for s in presentes if s in claves_modelo]
    sin_modelo = [s for s in presentes if s not in claves_modelo]

    if not con_modelo:
        raise ErrorEsquemaPMML(
            "Ningún valor de la variable de enrutamiento coincide con los "
            f"segmentos declarados en la configuración.\n\n"
            f"Segmentos en el dataset: {', '.join(presentes[:20]) or '(ninguno)'}\n"
            f"Segmentos configurados: {', '.join(claves_modelo.keys())}\n\n"
            "Verifica que la columna seleccionada sea la correcta y que los "
            "identificadores coincidan exactamente."
        )

    resultados: List[pd.DataFrame] = []
    resumen: List[dict] = []
    reporte_global = ReporteCasteo()

    for indice, segmento in enumerate(con_modelo, start=1):
        evaluador = claves_modelo[segmento]
        mascara = df_trabajo[variable_segmento] == segmento
        bloque_crudo = df_trabajo.loc[mascara]

        esquema = esquema_externo or obtener_esquema_entrada(evaluador)
        bloque_tipado, reporte = aplicar_esquema(bloque_crudo, esquema)
        reporte_global.incidencias.extend(reporte.incidencias)
        reporte_global.columnas_convertidas = max(
            reporte_global.columnas_convertidas, reporte.columnas_convertidas
        )

        validar_cobertura(bloque_tipado, nombres_entrada(evaluador))
        bloque_puntuado = puntuar(evaluador, bloque_tipado, tamano_bloque=tamano_bloque)
        bloque_puntuado["segmento_ejecutado"] = segmento

        resultados.append(bloque_puntuado)
        resumen.append({"Segmento": segmento, "Registros evaluados": len(bloque_puntuado)})

        if callback_progreso is not None:
            callback_progreso(segmento, indice, len(con_modelo))

        del bloque_crudo, bloque_tipado
        gc.collect()

    df_final = pd.concat(resultados, axis=0).sort_index()

    for segmento in sin_modelo:
        conteo = int((df_trabajo[variable_segmento] == segmento).sum())
        resumen.append({"Segmento": f"{segmento} (SIN MODELO)", "Registros evaluados": 0})
        reporte_global.incidencias.append(
            {
                "Columna": variable_segmento,
                "Tipo destino": "enrutamiento",
                "Valores no convertibles": conteo,
                "% del total": round(100.0 * conteo / max(len(df_trabajo), 1), 3),
            }
        )

    primer_evaluador = claves_modelo[con_modelo[0]]
    campos_salida = [str(c.getName()) for c in primer_evaluador.getOutputFields()]

    # Registros de segmentos sin modelo: nunca entraron al scoring.
    no_evaluados = sum(
        int((df_trabajo[variable_segmento] == s).sum()) for s in sin_modelo
    )

    return ResultadoScoring(
        datos=df_final,
        campos_entrada=nombres_entrada(primer_evaluador),
        campos_salida=campos_salida,
        reporte_casteo=reporte_global,
        filas_procesadas=len(df_final),
        filas_con_error=0,
        filas_sin_score=contar_sin_score(df_final, campos_salida) + no_evaluados,
        resumen_segmentos=pd.DataFrame(resumen),
    )
