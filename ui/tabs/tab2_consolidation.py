"""
ui.tabs.tab2_consolidation
==========================
Conciliacion entre el scoring calculado en Python (PMML) y el que produce la
plataforma de decision (Power Curve), con un tercer origen opcional de cifras
de control.

Sobre la logica de union
------------------------
El cruce reproduce **literalmente** el de la aplicacion original:

  * Una unica llave primaria, elegida sobre las columnas del archivo PMML, que
    debe existir con el mismo nombre en Power Curve una vez retirado el prefijo.
  * Retirada del prefijo con `str.replace`, no con un recorte por posicion.
  * Filtro de columnas por coincidencia de subcadena en minusculas:
    probability, target, segment, score, ademas de la propia llave.
  * Prefijos de salida `pwc_` y `CifrasControl_`.
  * Normalizacion de la llave con `clean_primary_key`.
  * `pd.merge(..., how="left")`, sin validacion de cardinalidad.

Esa logica se mantiene sin alterar porque define que registros emparejan y, en
consecuencia, el resultado de la validacion de implantacion. Lo unico que
cambia respecto de la version original es la presentacion.
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from core.data_utils import clean_primary_key
from ui import components as comp

# Criterio original de seleccion de columnas de resultado.
PATRONES_INTERES = ("probability", "target", "segment", "score")


def _leer_archivo(archivo) -> pd.DataFrame:
    """Lectura equivalente a la original: CSV o Parquet, con tipos inferidos."""
    if archivo.name.endswith(".csv"):
        return pd.read_csv(archivo)
    return pd.read_parquet(archivo)


def _columnas_a_conservar(df: pd.DataFrame, pk_col: str) -> list:
    """Filtro original: columnas de resultado mas la llave primaria."""
    return [
        col for col in df.columns
        if any(p in str(col).lower() for p in PATRONES_INTERES) or col == pk_col
    ]


def render() -> None:
    comp.seccion("2.1", "Carga de los orígenes a conciliar",
                 "Se requieren al menos dos orígenes")

    col_a, col_b, col_c = st.columns(3)
    with col_a:
        st.markdown("**Resultados PMML (Python)**")
        file_pmml_res = st.file_uploader(
            "Origen 1", type=["csv", "parquet"], key="f_pmml",
            label_visibility="collapsed",
        )
    with col_b:
        st.markdown("**Resultados Power Curve**")
        file_pwc = st.file_uploader(
            "Origen 2", type=["csv", "parquet"], key="f_pwc",
            label_visibility="collapsed",
        )
    with col_c:
        st.markdown("**Cifras de control** (opcional)")
        file_cifras = st.file_uploader(
            "Origen 3", type=["csv", "parquet"], key="f_cifras",
            label_visibility="collapsed",
        )

    if not (file_pmml_res and file_pwc):
        comp.vacio("Carga los dos orígenes obligatorios para desplegar la "
                   "configuración del cruce.")
        _mostrar_consolidado()
        return

    # ---------------------------------------------------------------- lectura
    try:
        df_pmml = _leer_archivo(file_pmml_res)
        df_pwc_raw = _leer_archivo(file_pwc)
    except Exception as exc:
        st.error(f"Error al leer los archivos base cargados: {exc}")
        return

    comp.kpis([
        {"etiqueta": "Registros PMML", "valor": f"{len(df_pmml):,}",
         "nota": f"{df_pmml.shape[1]} columnas"},
        {"etiqueta": "Registros Power Curve", "valor": f"{len(df_pwc_raw):,}",
         "nota": f"{df_pwc_raw.shape[1]} columnas", "estilo": "aqua"},
    ])

    # ---------------------------------------------------------- configuración
    comp.seccion("2.2", "Configuración del cruce")

    col_cfg1, col_cfg2 = st.columns(2)
    with col_cfg1:
        pk_col = st.selectbox(
            "Variable de comparación (llave primaria)",
            options=df_pmml.columns.tolist(),
            help="Debe existir con el mismo nombre en Power Curve una vez "
                 "retirado el prefijo.",
        )
    with col_cfg2:
        prefix_to_remove = st.text_input(
            "Prefijo a eliminar en las variables de Power Curve",
            placeholder="Ej.: PWC_",
        )

    comp.seccion("2.3", "Ejecución de la unión")

    if st.button("Ejecutar merge / conciliación", type="primary",
                 use_container_width=True, key="btn_merge"):
        with st.spinner("Procesando cruce de información y renombrado "
                        "dinámico de variables..."):
            try:
                df_pwc = df_pwc_raw.copy()

                if prefix_to_remove.strip():
                    df_pwc.columns = [
                        col.replace(prefix_to_remove, "")
                        if col.startswith(prefix_to_remove) else col
                        for col in df_pwc.columns
                    ]

                if pk_col not in df_pwc.columns:
                    st.error(
                        f"La llave «{pk_col}» no existe en Power Curve tras "
                        "eliminar el prefijo. Revisa el prefijo indicado o el "
                        "nombre de la columna."
                    )
                    return

                pwc_keep_cols = _columnas_a_conservar(df_pwc, pk_col)
                df_pwc_filtered = df_pwc[pwc_keep_cols].copy()
                df_pwc_filtered.columns = [
                    f"pwc_{col}" if col != pk_col else col
                    for col in df_pwc_filtered.columns
                ]

                # Limpieza homologada de la llave en ambos orígenes.
                df_pmml[pk_col] = clean_primary_key(df_pmml[pk_col])
                df_pwc_filtered[pk_col] = clean_primary_key(df_pwc_filtered[pk_col])

                df_final = pd.merge(df_pmml, df_pwc_filtered, on=pk_col, how="left")

                if file_cifras:
                    df_cifras = _leer_archivo(file_cifras)
                    cifras_keep_cols = _columnas_a_conservar(df_cifras, pk_col)
                    df_cifras_filtered = df_cifras[cifras_keep_cols].copy()
                    df_cifras_filtered.columns = [
                        f"CifrasControl_{col}" if col != pk_col else col
                        for col in df_cifras_filtered.columns
                    ]
                    df_cifras_filtered[pk_col] = clean_primary_key(
                        df_cifras_filtered[pk_col]
                    )
                    df_final = pd.merge(df_final, df_cifras_filtered,
                                        on=pk_col, how="left")

                st.session_state.matriz_consolidada = df_final
                st.session_state.llave_consolidada = pk_col

                st.success(
                    "Merge finalizado con éxito. Dimensiones del set "
                    f"consolidado: {df_final.shape[0]:,} registros."
                )
            except Exception as exc:
                st.error(f"Fallo en la matriz lógica de unión: {exc}")
                return

    _mostrar_consolidado()


def _mostrar_consolidado() -> None:
    consolidado = st.session_state.get("matriz_consolidada")
    if consolidado is None:
        return

    comp.seccion("2.4", "Matriz consolidada")

    columnas_pwc = [c for c in consolidado.columns if c.startswith("pwc_")]
    emparejados = (
        int(consolidado[columnas_pwc[0]].notna().sum()) if columnas_pwc else 0
    )
    tasa = 100.0 * emparejados / max(len(consolidado), 1)

    comp.kpis([
        {"etiqueta": "Registros consolidados", "valor": f"{len(consolidado):,}"},
        {"etiqueta": "Emparejados", "valor": f"{emparejados:,}",
         "nota": f"{tasa:.1f}% del total",
         "estilo": "exito" if tasa >= 90 else "alerta"},
        {"etiqueta": "Sin correspondencia",
         "valor": f"{len(consolidado) - emparejados:,}",
         "nota": "No hallados en Power Curve",
         "estilo": "riesgo" if tasa < 90 else ""},
        {"etiqueta": "Columnas", "valor": consolidado.shape[1], "estilo": "aqua"},
    ])

    if columnas_pwc and tasa < 90:
        st.warning(
            f"Solo se emparejó el {tasa:.1f}% de los registros. Revisa la "
            "llave primaria y el prefijo configurados."
        )

    comp.tabla(consolidado.head(500), altura=420, ocultar_indice=False)
    st.caption("Vista previa de las primeras 500 filas. La descarga incluye el total.")
    comp.descargas(consolidado, "matriz_consolidada_scoring", clave="consolidada")
    st.info("La matriz queda disponible en la pestaña **Análisis comparativo**.")
