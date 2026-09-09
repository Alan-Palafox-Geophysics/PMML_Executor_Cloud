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

from core.data_utils import a_excel_bytes


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
    """
    Botonera de exportacion en CSV y Excel, generada BAJO DEMANDA.

    `st.download_button` exige los bytes en el momento de dibujarse, asi que
    pasarle `a_csv_bytes(df)` directamente serializa el dataframe completo en
    CADA re-ejecucion del script: al cambiar de pestana, al pulsar cualquier
    control y tambien despues de la propia descarga. Con cientos de miles de
    registros eso son varios segundos de CPU y cientos de MB por interaccion,
    y es lo que hacia que la aplicacion se bloqueara.

    Aqui la serializacion se dispara solo cuando el usuario la pide, y los
    bytes quedan en la sesion para que las re-ejecuciones siguientes no
    repitan el trabajo.
    """
    if df is None or df.empty:
        return

    estado_csv = f"_export_csv_{clave}"
    estado_xlsx = f"_export_xlsx_{clave}"
    filas = len(df)

    columnas = st.columns(2 if incluir_excel else 1)

    # --------------------------------------------------------------- CSV
    with columnas[0]:
        if st.session_state.get(estado_csv) is None:
            st.download_button(
                "Descargar CSV",
                data=st.session_state[estado_csv],
                file_name=f"{nombre_base}.csv",
                mime="text/csv; charset=utf-8",
                use_container_width=True,
                key=f"csv_{clave}",
            )

        else :
            if st.button(f"Preparar CSV ({filas:,} filas)",
                         use_container_width=True, key=f"prep_csv_{clave}"):
                with st.spinner("Generando el archivo CSV..."):
                    # Generar bytes directamente desde pandas para garantizar:
                    # - índice fuera del archivo
                    # - UTF-8 con BOM (abre correctamente acentos/ñ en Excel)
                    # - salto de línea estándar
                    # - conservación exacta de las columnas y datos
                    st.session_state[estado_csv] = df.to_csv(
                        index=False,
                        encoding="utf-8-sig",
                        lineterminator="\\n",
                    ).encode("utf-8-sig")
                st.rerun()
        

    # ------------------------------------------------------------- Excel
    if incluir_excel:
        with columnas[1]:
            if st.session_state.get(estado_xlsx) is None:
                if st.button("Preparar Excel", use_container_width=True,
                             key=f"prep_xlsx_{clave}",
                             help="Más lento que el CSV en volúmenes grandes."):
                    try:
                        with st.spinner("Generando el archivo..."):
                            st.session_state[estado_xlsx] = a_excel_bytes(df)
                        st.rerun()
                    except Exception as exc:
                        st.error(f"No fue posible generar el Excel: {exc}")
            else:
                st.download_button(
                    "Descargar Excel",
                    data=st.session_state[estado_xlsx],
                    file_name=f"{nombre_base}.xlsx",
                    mime=(
                        "application/vnd.openxmlformats-officedocument."
                        "spreadsheetml.sheet"
                    ),
                    use_container_width=True,
                    key=f"xlsx_{clave}",
                )


def limpiar_exportaciones() -> None:
    """Descarta los archivos de exportacion ya generados en la sesion."""
    for clave in [k for k in st.session_state if str(k).startswith("_export_")]:
        st.session_state[clave] = None


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


def estado_motor(estado, mostrar_diagnostico: bool = False) -> None:
    """
    Panel de estado del entorno de ejecucion Java.

    El detalle tecnico (rutas del sistema, version de la JVM) solo se muestra a
    los perfiles con permiso de diagnostico: expone informacion de
    infraestructura que no aporta al analista y si a quien quiera sondear el
    entorno.
    """
    if estado.disponible:
        st.markdown(
            pastilla("Motor Java activo", "ok")
            + pastilla(f"JPMML {estado.version_jpmml}", "info"),
            unsafe_allow_html=True,
        )
        if not mostrar_diagnostico:
            return
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
            "Verifica que `jdk4py==21.0.8.2` figure en `requirements.txt` y que "
            "la instalación de dependencias haya terminado sin errores. Si "
            "acabas de añadirlo, reinicia la aplicación desde "
            "**Manage app → ⋮ → Reboot app**."
        )
        if mostrar_diagnostico:
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
