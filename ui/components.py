"""
ui.components
=============
Componentes visuales reutilizables. Centralizarlos evita que el HTML se
disperse por las pestanas y garantiza que toda la aplicacion hable el mismo
lenguaje visual.
"""

from __future__ import annotations

from typing import Iterable, Optional, Sequence

import pandas as pd
import streamlit as st

from core.data_utils import a_csv_bytes, a_excel_bytes


def cabecera(titulo: str, descripcion: str, etiqueta: str = "Risk Analytics") -> None:
    """Banda superior corporativa de la aplicacion."""
    st.markdown(
        f"""
        <div class="bbva-header">
            <div class="bbva-marca">{etiqueta}</div>
            <h1>{titulo}</h1>
            <p>{descripcion}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )


def seccion(indice: str, titulo: str, subtitulo: str = "") -> None:
    """Encabezado de seccion numerado."""
    st.markdown(
        f"""
        <div class="seccion">
            <div class="indice">{indice}</div>
            <div class="titulo">{titulo}</div>
            <div class="subtitulo">{subtitulo}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def kpis(tarjetas: Sequence[dict]) -> None:
    """
    Fila de indicadores.

    Cada tarjeta admite: etiqueta, valor, nota y estilo
    ('', 'aqua', 'exito', 'alerta', 'riesgo').
    """
    bloques = []
    for tarjeta in tarjetas:
        estilo = tarjeta.get("estilo", "")
        nota = tarjeta.get("nota", "")
        bloques.append(
            f"""<div class="kpi {estilo}">
                    <div class="etiqueta">{tarjeta.get('etiqueta','')}</div>
                    <div class="valor">{tarjeta.get('valor','—')}</div>
                    <div class="nota">{nota}</div>
                </div>"""
        )
    st.markdown(f'<div class="kpi-grid">{"".join(bloques)}</div>', unsafe_allow_html=True)


def pastilla(texto: str, tipo: str = "info") -> str:
    """Devuelve el HTML de una etiqueta de estado (ok | no | info)."""
    return f'<span class="pastilla {tipo}">{texto}</span>'


def tabla(df: pd.DataFrame, altura: Optional[int] = None, ocultar_indice: bool = True) -> None:
    """
    Renderiza un DataFrame de forma segura.

    Los tipos anulables de pandas (Int64, boolean, string) y las columnas con
    objetos Java no siempre son serializables por Arrow, asi que se normaliza a
    texto cuando la conversion directa falla. Esto evita el error de
    renderizado que aparece al mostrar resultados crudos del evaluador.
    """
    if df is None or df.empty:
        st.caption("Sin registros para mostrar.")
        return

    parametros = {"use_container_width": True, "hide_index": ocultar_indice}
    if altura:
        parametros["height"] = altura

    try:
        st.dataframe(df, **parametros)
    except Exception:
        st.dataframe(df.astype(str), **parametros)


def descargas(
    df: pd.DataFrame,
    nombre_base: str,
    clave: str,
    incluir_excel: bool = True,
) -> None:
    """Botonera de exportacion en CSV y Excel."""
    if df is None or df.empty:
        return

    columnas = st.columns(2 if incluir_excel else 1)
    with columnas[0]:
        st.download_button(
            "Descargar CSV",
            data=a_csv_bytes(df),
            file_name=f"{nombre_base}.csv",
            mime="text/csv",
            use_container_width=True,
            key=f"csv_{clave}",
        )

    if incluir_excel:
        with columnas[1]:
            try:
                contenido = a_excel_bytes(df)
            except Exception:
                contenido = None
            if contenido is not None:
                st.download_button(
                    "Descargar Excel",
                    data=contenido,
                    file_name=f"{nombre_base}.xlsx",
                    mime=(
                        "application/vnd.openxmlformats-officedocument."
                        "spreadsheetml.sheet"
                    ),
                    use_container_width=True,
                    key=f"xlsx_{clave}",
                )


def aviso_calidad(reporte) -> None:
    """Muestra el reporte de casteo cuando hubo perdidas de informacion."""
    if reporte is None or not reporte.hay_incidencias:
        return

    with st.expander("Incidencias de conversión de tipos", expanded=False):
        if reporte.columnas_ausentes:
            st.warning(
                "Variables del esquema que no existen en el archivo: "
                + ", ".join(reporte.columnas_ausentes)
            )
        detalle = reporte.como_dataframe()
        if not detalle.empty:
            st.caption(
                "Valores que no pudieron convertirse al tipo esperado y quedaron "
                "como nulos. En un proceso de riesgo conviene revisarlos antes de "
                "dar el scoring por válido."
            )
            tabla(detalle)


def estado_motor(estado) -> None:
    """Panel de diagnostico del entorno de ejecucion Java."""
    if estado.disponible:
        st.markdown(
            pastilla("Motor Java activo", "ok")
            + pastilla(f"JPMML {estado.version_jpmml}", "info"),
            unsafe_allow_html=True,
        )
        with st.expander("Detalle del entorno de ejecución", expanded=False):
            st.write(f"**Runtime:** {estado.version_java or 'no identificado'}")
            st.write(f"**JAVA_HOME:** `{estado.java_home}`")
            for linea in estado.diagnostico:
                st.caption(f"• {linea}")
    else:
        st.markdown(pastilla("Motor Java no disponible", "no"), unsafe_allow_html=True)
        st.error(
            "No se pudo inicializar la máquina virtual de Java, necesaria para "
            "evaluar modelos PMML.\n\n"
            f"**Detalle:** {estado.detalle_error}\n\n"
            "Verifica que el archivo `packages.txt` esté en la raíz del "
            "repositorio con el contenido `openjdk-17-jre-headless` y reinicia "
            "la aplicación desde el panel de Streamlit Cloud."
        )
        for linea in estado.diagnostico:
            st.caption(f"• {linea}")


def vacio(mensaje: str, icono: str = "○") -> None:
    """Estado vacio discreto para secciones sin datos aun."""
    st.markdown(
        f"""
        <div style="text-align:center;padding:2.2rem 1rem;color:#5A6474;
                    background:#FFFFFF;border:1px dashed #DDE3EC;border-radius:11px;">
            <div style="font-size:1.7rem;margin-bottom:.4rem;opacity:.45;">{icono}</div>
            <div style="font-size:.9rem;">{mensaje}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
