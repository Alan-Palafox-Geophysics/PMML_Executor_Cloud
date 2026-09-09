"""
PMML Risk Workspace
===================
Entorno de ejecucion, conciliacion y validacion de modelos PMML para riesgo
de credito.

Punto de entrada de la aplicacion Streamlit.

Notas de arquitectura
---------------------
* Los paquetes se llaman `core` y `ui`. La version anterior tenia `app.py` y
  una carpeta `app/` conviviendo en la raiz, lo que hace ambiguo el import de
  `app` y obligaba a manipular `sys.path` a mano. Con nombres distintos, los
  imports funcionan sin trucos tanto en local como en Streamlit Cloud.
* La JVM se inicializa una unica vez por proceso mediante `st.cache_resource`,
  porque JPype no admite reiniciarla y Streamlit re-ejecuta el script completo
  en cada interaccion del usuario.
"""

from __future__ import annotations

import gc

import streamlit as st

# La configuracion de pagina debe ser la primera llamada a Streamlit.
st.set_page_config(
    page_title="PMML Risk Workspace",
    page_icon="◆",
    layout="wide",
    initial_sidebar_state="expanded",
    menu_items={"about": "Entorno de validación de modelos PMML — Riesgo de crédito"},
)

from core import jvm  # noqa: E402
from core.auth import autenticar, hay_credenciales_configuradas  # noqa: E402
from ui import components as comp  # noqa: E402
from ui.tabs import (  # noqa: E402
    tab1_execution,
    tab2_consolidation,
    tab3_analysis,
    tab4_roadmap,
)
from ui.theme import aplicar_estilos  # noqa: E402

aplicar_estilos()


# --------------------------------------------------------------------------
# Motor Java
# --------------------------------------------------------------------------
@st.cache_resource(show_spinner="Inicializando el motor de evaluación PMML...")
def arrancar_motor():
    """Arranca la JVM una sola vez por proceso y memoiza el resultado."""
    return jvm.iniciar_jvm()


# --------------------------------------------------------------------------
# Estado de sesión
# --------------------------------------------------------------------------
VALORES_INICIALES = {
    "autenticado": False,
    "usuario": None,
    "rol": None,
    "permisos": set(),
    "resultado_scoring": None,
    "matriz_consolidada": None,
    "llave_consolidada": None,
}
for clave, valor in VALORES_INICIALES.items():
    st.session_state.setdefault(clave, valor)


# --------------------------------------------------------------------------
# Autenticación
# --------------------------------------------------------------------------
def pantalla_acceso() -> None:
    """Pantalla de control de acceso."""
    _, centro, _ = st.columns([1, 1.5, 1])
    with centro:
        st.markdown(
            """
            <div style="text-align:center;margin:2.2rem 0 1.4rem 0;">
                <div style="font-size:2.05rem;font-weight:800;color:#072146;
                            letter-spacing:.04em;">PMML RISK WORKSPACE</div>
                <div style="font-size:.72rem;letter-spacing:.19em;color:#2DCCCD;
                            text-transform:uppercase;font-weight:700;
                            margin-top:.3rem;">
                    Validación de modelos · Riesgo de crédito
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        st.markdown('<div class="tarjeta-login">', unsafe_allow_html=True)
        st.markdown("### Control de acceso")
        st.markdown(
            '<p style="color:#5A6474;font-size:.86rem;">Introduce tus '
            "credenciales corporativas para acceder al entorno.</p>",
            unsafe_allow_html=True,
        )

        with st.form("formulario_acceso"):
            usuario = st.text_input("Usuario", placeholder="usuario corporativo")
            contrasena = st.text_input("Contraseña", type="password",
                                       placeholder="••••••••")
            enviar = st.form_submit_button("Acceder", type="primary",
                                           use_container_width=True)

        st.markdown("</div>", unsafe_allow_html=True)

        if enviar:
            if not hay_credenciales_configuradas():
                st.error(
                    "No hay credenciales configuradas. En Streamlit Cloud, "
                    "abre **Manage app → Settings → Secrets** y añade la "
                    "sección `[usuarios]`. En local, crea el archivo "
                    "`.streamlit/secrets.toml`."
                )
            else:
                identidad = autenticar(usuario, contrasena)
                if identidad is not None:
                    st.session_state.autenticado = True
                    st.session_state.usuario = identidad
                    st.session_state.rol = identidad.rol
                    st.session_state.permisos = identidad.permisos
                    st.rerun()
                else:
                    st.error("Usuario o contraseña incorrectos.")


if not st.session_state.autenticado:
    pantalla_acceso()
    st.stop()


# --------------------------------------------------------------------------
# Aplicación
# --------------------------------------------------------------------------
estado_jvm = arrancar_motor()

with st.sidebar:
    st.markdown(
        """
        <div class="barra-lateral-marca">
            <div class="logo">PMML</div>
            <div class="sub">Risk Workspace</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    submodulo = st.radio(
        "Módulo de ejecución",
        options=[
            "1.1 Auditoría de metadatos",
            "1.2 Scoring de modelo único",
            "1.3 Scoring multimodelo",
        ],
        help="Selecciona la vista activa dentro de la pestaña «Ejecución».",
    )

    st.markdown("---")
    st.markdown("**Estado del entorno**")

    if estado_jvm.disponible:
        st.markdown(
            f"<span style='color:#2DCCCD;font-weight:600;'>● Motor Java activo</span>"
            f"<br><span style='font-size:.75rem;opacity:.75;'>"
            f"JPMML {estado_jvm.version_jpmml}</span>",
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            "<span style='color:#F7893B;font-weight:600;'>● Motor Java no disponible</span>",
            unsafe_allow_html=True,
        )

    if st.session_state.resultado_scoring is not None:
        st.caption(f"Scoring en memoria: {len(st.session_state.resultado_scoring):,} filas")
    if st.session_state.matriz_consolidada is not None:
        st.caption(f"Matriz consolidada: {len(st.session_state.matriz_consolidada):,} filas")

    # ------------------------------------------------------ memoria de la JVM
    if estado_jvm.disponible:
        memoria = jvm.memoria_java()
        if memoria:
            st.markdown("**Memoria del motor Java**")
            st.progress(
                min(memoria["uso_pct"] / 100.0, 1.0),
                text=f"{memoria['en_uso_mb']} / {memoria['maxima_mb']} MB "
                     f"({memoria['uso_pct']}%)",
            )
            if memoria["uso_pct"] > 80:
                st.caption(
                    "Uso elevado. Libera memoria o reduce el tamaño de bloque "
                    "antes de lanzar una corrida grande."
                )

        if st.button("Liberar memoria", use_container_width=True,
                     help="Vacía la caché de modelos y fuerza la recolección "
                          "de basura en la JVM. Los resultados ya calculados "
                          "se conservan."):
            tab1_execution.liberar_cache_modelos()
            gc.collect()
            st.rerun()

    st.markdown("---")
    identidad = st.session_state.usuario
    st.caption(f"Sesión: **{identidad.id}**")
    st.caption(f"Perfil: **{identidad.etiqueta_rol}**")
    if st.button("Cerrar sesión", use_container_width=True):
        for clave in VALORES_INICIALES:
            st.session_state[clave] = VALORES_INICIALES[clave]
        st.rerun()


comp.cabecera(
    "PMML Risk Workspace",
    "Ejecución de modelos PMML, conciliación con la plataforma de decisión y "
    "análisis de desviaciones para la validación de implantaciones de riesgo "
    "de crédito.",
)

if not estado_jvm.disponible:
    comp.estado_motor(estado_jvm, mostrar_diagnostico=True)

pestanas = st.tabs([
    "Ejecución de modelos",
    "Conciliación",
    "Análisis comparativo",
    "Hoja de ruta",
])

with pestanas[0]:
    tab1_execution.render(submodulo, estado_jvm, st.session_state.usuario)

with pestanas[1]:
    tab2_consolidation.render()

with pestanas[2]:
    tab3_analysis.render()

with pestanas[3]:
    tab4_roadmap.render()
