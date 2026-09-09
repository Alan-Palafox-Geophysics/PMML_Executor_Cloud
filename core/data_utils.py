"""
core.data_utils
===============
Lectura de datasets y conversion de tipos tolerante a las imperfecciones
tipicas de los extractos de riesgo de credito.

El casteo es el punto mas fragil de todo el pipeline. La version original hacia
`Series.astype("Int64")` directamente sobre texto, lo que revienta con el caso
mas frecuente en la practica: una columna entera exportada desde pandas con
nulos, que queda escrita como "35.0" en el CSV. Aqui se normaliza antes de
convertir y se registra cuantos valores se perdieron en el intento, de modo que
el analista pueda auditar la conversion en lugar de confiar a ciegas.
"""

from __future__ import annotations

import io
import re
from dataclasses import dataclass, field
from typing import Dict, Optional, Tuple, Union

import numpy as np
import pandas as pd

# Mapa PMML -> pandas. `Int64` (nullable) permite enteros con faltantes, cosa
# que el int64 clasico de numpy no soporta.
MAPA_TIPOS_PMML = {
    "double": "float64",
    "float": "float32",
    "integer": "Int64",
    "int": "Int64",
    "string": "string",
    "boolean": "boolean",
    "date": "string",
    "dateTime": "string",
}

_VALORES_NULOS = {
    "", "nan", "NaN", "NAN", "null", "NULL", "None", "none",
    "NA", "na", "N/A", "n/a", "<NA>", ".", "-", "?",
}

_MAPA_BOOLEANO = {
    "true": True, "t": True, "yes": True, "y": True, "si": True, "s": True,
    "1": True, "1.0": True, "verdadero": True,
    "false": False, "f": False, "no": False, "n": False,
    "0": False, "0.0": False, "falso": False,
}


@dataclass
class ReporteCasteo:
    """Traza auditable de la conversion de tipos de un dataset."""

    columnas_convertidas: int = 0
    columnas_ausentes: list[str] = field(default_factory=list)
    incidencias: list[dict] = field(default_factory=list)

    def registrar_perdida(self, columna: str, tipo: str, nulos_nuevos: int, total: int) -> None:
        if nulos_nuevos > 0:
            self.incidencias.append(
                {
                    "Columna": columna,
                    "Tipo destino": tipo,
                    "Valores no convertibles": nulos_nuevos,
                    "% del total": round(100.0 * nulos_nuevos / max(total, 1), 3),
                }
            )

    @property
    def hay_incidencias(self) -> bool:
        return bool(self.incidencias) or bool(self.columnas_ausentes)

    def como_dataframe(self) -> pd.DataFrame:
        return pd.DataFrame(self.incidencias)


def leer_tabla(
    origen: Union[str, bytes, io.BytesIO],
    nombre: str = "",
    como_texto: bool = True,
) -> pd.DataFrame:
    """
    Lee un CSV o Parquet desde ruta o buffer.

    Los CSV se leen como texto (`dtype=str`) a proposito: dejar que pandas
    infiera los tipos antes de conocer el esquema del PMML produce silenciosas
    perdidas de ceros a la izquierda en identificadores y conversiones a float
    de campos que el modelo espera categoricos.
    """
    nombre_normalizado = (nombre or str(origen)).lower()

    if nombre_normalizado.endswith(".parquet"):
        return pd.read_parquet(origen)

    if isinstance(origen, bytes):
        origen = io.BytesIO(origen)

    opciones = {
        "keep_default_na": False,
        "na_values": list(_VALORES_NULOS),
        "low_memory": False,
    }
    if como_texto:
        opciones["dtype"] = str

    try:
        return pd.read_csv(origen, **opciones)
    except UnicodeDecodeError:
        if hasattr(origen, "seek"):
            origen.seek(0)
        # Los extractos de core bancario suelen venir en Latin-1.
        return pd.read_csv(origen, encoding="latin-1", **opciones)


def leer_diccionario_tipos(origen, nombre: str = "") -> Optional[Dict[str, str]]:
    """
    Lee un diccionario de tipos externo (dos columnas: variable, tipo).

    Permite forzar un esquema distinto al declarado en el PMML, algo habitual
    cuando el extracto de origen ya viene tipado desde el datalake.
    """
    if origen is None:
        return None
    df_tipos = leer_tabla(origen, nombre=nombre, como_texto=False)
    if df_tipos.shape[1] < 2:
        raise ValueError(
            "El diccionario de tipos debe tener al menos dos columnas "
            "(nombre de variable y tipo de dato)."
        )
    columnas = df_tipos.iloc[:, 0].astype(str).str.strip()
    tipos = df_tipos.iloc[:, 1].astype(str).str.strip()
    return dict(zip(columnas, tipos))


def _normalizar_texto(serie: pd.Series) -> pd.Series:
    """Convierte a texto limpio y unifica todos los marcadores de nulo."""
    limpia = serie.astype("string").str.strip()
    return limpia.replace(list(_VALORES_NULOS), pd.NA)


def _a_numerico(serie: pd.Series) -> pd.Series:
    """
    Convierte texto a numero tolerando formatos de exportacion habituales:
    separadores de miles, coma decimal, signos de porcentaje y parentesis
    contables para negativos.
    """
    texto = _normalizar_texto(serie)

    # Negativos en notacion contable: (1234) -> -1234
    texto = texto.str.replace(r"^\((.*)\)$", r"-\1", regex=True)
    texto = texto.str.replace("%", "", regex=False)
    texto = texto.str.replace(r"\s", "", regex=True)

    # Coma decimal europea: 1.234,56 -> 1234.56 (solo si hay punto y coma).
    tiene_ambos = texto.str.contains(r"\.", na=False) & texto.str.contains(",", na=False)
    texto = texto.mask(
        tiene_ambos,
        texto.str.replace(".", "", regex=False).str.replace(",", ".", regex=False),
    )
    # Coma como unico separador decimal: 1234,56 -> 1234.56
    solo_coma = texto.str.contains(",", na=False) & ~texto.str.contains(r"\.", na=False)
    texto = texto.mask(solo_coma, texto.str.replace(",", ".", regex=False))

    return pd.to_numeric(texto, errors="coerce")


def convertir_serie(serie: pd.Series, tipo_destino: str) -> pd.Series:
    """Convierte una serie al tipo pandas indicado sin lanzar excepciones."""
    tipo = MAPA_TIPOS_PMML.get(tipo_destino, tipo_destino)

    if tipo in ("boolean", "bool"):
        texto = _normalizar_texto(serie).str.lower()
        return texto.map(_MAPA_BOOLEANO).astype("boolean")

    if tipo in ("Int64", "int64", "Int32", "int32"):
        # Clave del arreglo: pasar por float y redondear antes de enteros, de
        # forma que "35.0" -> 35 en lugar de reventar la conversion.
        numerico = _a_numerico(serie)
        return numerico.round().astype("Int64")

    if tipo in ("float64", "float32", "float"):
        return _a_numerico(serie).astype(tipo if tipo != "float" else "float64")

    if tipo in ("string", "object", "str"):
        texto = _normalizar_texto(serie)
        # Un identificador leido como float ("12345.0") debe volver a "12345",
        # o el cruce por llave primaria fallara silenciosamente.
        parece_entero = texto.str.fullmatch(r"-?\d+\.0+", na=False)
        texto = texto.mask(parece_entero, texto.str.replace(r"\.0+$", "", regex=True))
        return texto

    return serie.astype("string")


def aplicar_esquema(
    df: pd.DataFrame, esquema: Dict[str, str]
) -> Tuple[pd.DataFrame, ReporteCasteo]:
    """
    Aplica un esquema de tipos al DataFrame y devuelve el reporte de conversion.

    A diferencia de la version original, una columna problematica no aborta el
    proceso completo: se convierte lo convertible, los valores irrecuperables
    quedan como nulos y todo queda registrado en el reporte.
    """
    resultado = df.copy()
    reporte = ReporteCasteo()

    for columna, tipo in esquema.items():
        if columna not in resultado.columns:
            reporte.columnas_ausentes.append(columna)
            continue

        original = resultado[columna]
        nulos_antes = int(original.isna().sum())
        convertida = convertir_serie(original, tipo)
        nulos_despues = int(convertida.isna().sum())

        resultado[columna] = convertida
        reporte.columnas_convertidas += 1
        reporte.registrar_perdida(
            columna, tipo, nulos_despues - nulos_antes, len(resultado)
        )

    return resultado, reporte


def clean_primary_key(series: pd.Series) -> pd.Series:
    """
    Limpia las llaves primarias antes de hacer merge.

    Replica exactamente el comportamiento de la aplicacion original:
    convierte a texto, elimina el sufijo «.0» heredado de una lectura como
    float y recorta espacios. Es la unica normalizacion aplicada a la llave en
    la conciliacion, y se mantiene literal a proposito: cualquier variacion
    (tratar los nulos como pd.NA, recortar «.00», normalizar mayusculas)
    cambia el conjunto de registros que emparejan y, por tanto, el resultado
    de la validacion.
    """
    return series.astype(str).str.replace(r"\.0$", "", regex=True).str.strip()


def limpiar_llave_primaria(serie: pd.Series) -> pd.Series:
    """
    Normaliza una llave primaria para que los cruces no fallen por formato.

    Homogeneiza el tipo a texto, elimina el sufijo ".0" heredado de lecturas
    como float y recorta espacios. Sin esto, un merge entre un extracto de
    Power Curve y uno de Python puede devolver cero coincidencias aun cuando
    las llaves son logicamente identicas.
    """
    texto = serie.astype("string").str.strip()
    parece_entero = texto.str.fullmatch(r"-?\d+\.0+", na=False)
    texto = texto.mask(parece_entero, texto.str.replace(r"\.0+$", "", regex=True))
    return texto.replace(list(_VALORES_NULOS), pd.NA)


def perfilar_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """Resumen compacto de calidad de datos para mostrar en la interfaz."""
    filas = len(df)
    registros = []
    for columna in df.columns:
        serie = df[columna]
        nulos = int(serie.isna().sum())
        registros.append(
            {
                "Variable": columna,
                "Tipo": str(serie.dtype),
                "Nulos": nulos,
                "% Nulos": round(100.0 * nulos / max(filas, 1), 2),
                "Valores únicos": int(serie.nunique(dropna=True)),
            }
        )
    return pd.DataFrame(registros)


def detectar_columnas_probabilidad(df: pd.DataFrame, prefijo: str = "") -> list[str]:
    """
    Localiza columnas de probabilidad o score generadas por los modelos.

    Se usa una heuristica amplia porque los exportadores de PMML no coinciden
    en la nomenclatura: sklearn2pmml produce `probability_1`, R produce
    `Probability_Yes` y algunos scorecards devuelven `score`.
    """
    patron = re.compile(r"(probability|probabilidad|score|puntaje|pd_|_pd$)", re.IGNORECASE)
    candidatas = []
    for columna in df.columns:
        if prefijo and not columna.startswith(prefijo):
            continue
        if not prefijo and any(
            columna.startswith(p) for p in ("pwc_", "cc_", "CifrasControl_")
        ):
            continue
        if patron.search(str(columna)):
            candidatas.append(columna)
    return candidatas


def a_csv_bytes(df: pd.DataFrame) -> bytes:
    """Serializa a CSV UTF-8 con BOM para que Excel respete los acentos."""
    return df.to_csv(index=False).encode("utf-8-sig")


def a_excel_bytes(df: pd.DataFrame, hoja: str = "Resultados") -> bytes:
    """Serializa a XLSX en memoria, truncando si excede el limite de Excel."""
    buffer = io.BytesIO()
    limite = 1_048_575
    recorte = df.head(limite) if len(df) > limite else df
    with pd.ExcelWriter(buffer, engine="openpyxl") as escritor:
        recorte.to_excel(escritor, index=False, sheet_name=hoja[:31])
    return buffer.getvalue()
