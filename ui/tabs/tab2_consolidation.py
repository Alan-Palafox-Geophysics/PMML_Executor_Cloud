"""
ui.tabs.tab2_consolidation
==========================
Conciliacion entre el scoring calculado en Python (PMML) y el que produce la
plataforma de decision (Power Curve), con un tercer origen opcional de cifras
de control.

Mejoras de fondo respecto de la version anterior:
  * La llave primaria se elige de forma independiente en cada archivo, en lugar
    de asumir que se llama igual en los tres. En la practica casi nunca coincide.
  * Se reporta la tasa de emparejamiento. Un merge que cruza el 3% de los
    registros antes se veia como un exito porque solo se mostraba el conteo de
    filas resultante.
  * `st.stop()` se elimina: dentro de una pestana detiene la aplicacion entera.
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from core.data_utils import leer_tabla, limpiar_llave_primaria
from ui import components as comp

PATRONES_INTERES = ("probability", "probabilidad", "score", "puntaje",
                    "target", "segment", "pd_", "rating", "grade")


def _columnas_relevantes(df: pd.DataFrame, llave: str) -> list[str]:
    """Selecciona las columnas de resultado que aportan a la conciliación."""
    seleccion = [llave]
    for columna in df.columns:
        if columna == llave:
            continue
        if any(p in str(columna).lower() for p in PATRONES_INTERES):
            seleccion.append(columna)
    return seleccion


def _preparar(df: pd.DataFrame, llave: str, prefijo: str,
              quitar_prefijo: str = "") -> pd.DataFrame:
    """Normaliza un origen: recorta prefijos, filtra columnas y renombra."""
    trabajo = df.copy()

    if quitar_prefijo.strip():
        trabajo.columns = [
            c[len(quitar_prefijo):] if str(c).startswith(quitar_prefijo) else c
            for c in trabajo.columns
        ]

    columnas = _columnas_relevantes(trabajo, llave)
    trabajo = trabajo[columnas].copy()
    trabajo.columns = [c if c == llave else f"{prefijo}{c}" for c in trabajo.columns]
    trabajo[llave] = limpiar_llave_primaria(trabajo[llave])
    return trabajo


def render() -> None:
    comp.seccion("2.1", "Carga de los orígenes a conciliar",
                 "Se requieren al menos dos orígenes")

    col_a, col_b, col_c = st.columns(3)
    with col_a:
        st.markdown("**Resultados PMML (Python)**")
        archivo_pmml = st.file_uploader("Origen 1", type=["csv", "parquet"],
                                        key="conc_pmml", label_visibility="collapsed")
        usar_sesion = st.checkbox(
            "Usar el último scoring ejecutado",
            value=False, key="conc_usar_sesion",
            disabled=st.session_state.get("resultado_scoring") is None,
            help="Toma directamente el resultado generado en la pestaña de ejecución.",
        )
    with col_b:
        st.markdown("**Resultados Power Curve**")
        archivo_pwc = st.file_uploader("Origen 2", type=["csv", "parquet"],
                                       key="conc_pwc", label_visibility="collapsed")
    with col_c:
        st.markdown("**Cifras de control** (opcional)")
        archivo_cifras = st.file_uploader("Origen 3", type=["csv", "parquet"],
                                          key="conc_cifras", label_visibility="collapsed")

    # ------------------------------------------------------------ lectura
    df_pmml = None
    if usar_sesion and st.session_state.get("resultado_scoring") is not None:
        df_pmml = st.session_state.resultado_scoring.copy()
    elif archivo_pmml is not None:
        try:
            df_pmml = leer_tabla(archivo_pmml.getvalue(), nombre=archivo_pmml.name,
                                 como_texto=False)
        except Exception as exc:
            st.error(f"No fue posible leer el archivo de resultados PMML: {exc}")

    df_pwc = None
    if archivo_pwc is not None:
        try:
            df_pwc = leer_tabla(archivo_pwc.getvalue(), nombre=archivo_pwc.name,
                                como_texto=False)
        except Exception as exc:
            st.error(f"No fue posible leer el archivo de Power Curve: {exc}")

    if df_pmml is None or df_pwc is None:
        comp.vacio("Carga los dos orígenes obligatorios para continuar.")
        return

    comp.kpis([
        {"etiqueta": "Registros PMML", "valor": f"{len(df_pmml):,}",
         "nota": f"{df_pmml.shape[1]} columnas"},
        {"etiqueta": "Registros Power Curve", "valor": f"{len(df_pwc):,}",
         "nota": f"{df_pwc.shape[1]} columnas", "estilo": "aqua"},
    ])

    # ------------------------------------------------------- configuración
    comp.seccion("2.2", "Configuración del cruce")

    col_d, col_e = st.columns(2)
    with col_d:
        llave_pmml = st.selectbox("Llave primaria en el archivo PMML",
                                  options=df_pmml.columns.tolist(), key="conc_k1")
    with col_e:
        # Se preselecciona una columna homónima si existe: es el caso frecuente.
        opciones_pwc = df_pwc.columns.tolist()
        indice = opciones_pwc.index(llave_pmml) if llave_pmml in opciones_pwc else 0
        llave_pwc = st.selectbox("Llave primaria en Power Curve",
                                 options=opciones_pwc, index=indice, key="conc_k2")

    col_f, col_g = st.columns(2)
    with col_f:
        prefijo_quitar = st.text_input(
            "Prefijo a eliminar en las columnas de Power Curve",
            placeholder="Ej.: PWC_",
            help="Se elimina antes del cruce para homologar los nombres.",
        )
    with col_g:
        tipo_union = st.selectbox(
            "Tipo de unión", options=["left", "inner", "outer"], index=0,
            help="«left» conserva todos los registros del scoring PMML.",
        )

    llave_cifras = None
    df_cifras = None
    if archivo_cifras is not None:
        try:
            df_cifras = leer_tabla(archivo_cifras.getvalue(),
                                   nombre=archivo_cifras.name, como_texto=False)
            opciones_cifras = df_cifras.columns.tolist()
            indice_c = (opciones_cifras.index(llave_pmml)
                        if llave_pmml in opciones_cifras else 0)
            llave_cifras = st.selectbox("Llave primaria en cifras de control",
                                        options=opciones_cifras, index=indice_c,
                                        key="conc_k3")
        except Exception as exc:
            st.error(f"No fue posible leer el archivo de cifras de control: {exc}")
            df_cifras = None

    if not st.button("Ejecutar conciliación", type="primary", key="btn_merge"):
        _mostrar_consolidado()
        return

    # ------------------------------------------------------------- proceso
    try:
        with st.spinner("Homologando llaves y cruzando los orígenes..."):
            izquierda = df_pmml.copy()
            izquierda[llave_pmml] = limpiar_llave_primaria(izquierda[llave_pmml])

            derecha = _preparar(df_pwc, llave_pwc, "pwc_", prefijo_quitar)
            if llave_pwc != llave_pmml:
                derecha = derecha.rename(columns={llave_pwc: llave_pmml})

            consolidado = pd.merge(izquierda, derecha, on=llave_pmml,
                                   how=tipo_union, validate="m:1")

            if df_cifras is not None and llave_cifras is not None:
                control = _preparar(df_cifras, llave_cifras, "cc_")
                if llave_cifras != llave_pmml:
                    control = control.rename(columns={llave_cifras: llave_pmml})
                consolidado = pd.merge(consolidado, control, on=llave_pmml,
                                       how=tipo_union)

        st.session_state.matriz_consolidada = consolidado
        st.session_state.llave_consolidada = llave_pmml

    except pd.errors.MergeError:
        st.error(
            "La llave elegida en Power Curve está duplicada, por lo que el cruce "
            "multiplicaría registros. Selecciona una llave única o depura el "
            "archivo antes de conciliar."
        )
        return
    except Exception as exc:
        st.error(f"La conciliación no pudo completarse.\n\n**Detalle:** {exc}")
        return

    columnas_pwc = [c for c in consolidado.columns if c.startswith("pwc_")]
    if columnas_pwc:
        emparejados = int(consolidado[columnas_pwc[0]].notna().sum())
    else:
        emparejados = 0
    tasa = 100.0 * emparejados / max(len(consolidado), 1)

    if tasa < 90:
        st.warning(
            f"Solo se emparejó el {tasa:.1f}% de los registros. Revisa que la "
            "llave primaria y el prefijo configurados sean los correctos."
        )
    else:
        st.success(f"Conciliación completada: {len(consolidado):,} registros.")

    _mostrar_consolidado()


def _mostrar_consolidado() -> None:
    consolidado = st.session_state.get("matriz_consolidada")
    if consolidado is None:
        return

    comp.seccion("2.3", "Matriz consolidada")

    columnas_pwc = [c for c in consolidado.columns if c.startswith("pwc_")]
    emparejados = (int(consolidado[columnas_pwc[0]].notna().sum())
                   if columnas_pwc else 0)
    tasa = 100.0 * emparejados / max(len(consolidado), 1)

    comp.kpis([
        {"etiqueta": "Registros consolidados", "valor": f"{len(consolidado):,}"},
        {"etiqueta": "Emparejados", "valor": f"{emparejados:,}",
         "nota": f"{tasa:.1f}% del total",
         "estilo": "exito" if tasa >= 90 else "alerta"},
        {"etiqueta": "Sin correspondencia", "valor": f"{len(consolidado)-emparejados:,}",
         "nota": "No hallados en Power Curve",
         "estilo": "riesgo" if tasa < 90 else ""},
        {"etiqueta": "Columnas", "valor": consolidado.shape[1], "estilo": "aqua"},
    ])

    comp.tabla(consolidado.head(500), altura=420, ocultar_indice=False)
    st.caption("Vista previa de las primeras 500 filas. La descarga incluye el total.")
    comp.descargas(consolidado, "matriz_consolidada", clave="consolidada")
    st.info("La matriz queda disponible en la pestaña **Análisis comparativo**.")
