"""
ui.theme
========
Identidad visual corporativa BBVA y estilos globales de la aplicacion.

La paleta se define una sola vez aqui y se reutiliza tanto en el CSS como en
los graficos de Plotly, de modo que la interfaz y las visualizaciones sean
cromaticamente consistentes.
"""

from __future__ import annotations

import streamlit as st

# ---------------------------------------------------------------- paleta
AZUL_NUCLEO = "#072146"      # Core Blue — fondo de cabeceras y navegacion
AZUL_MEDIO = "#1464A5"       # Medium Blue — color primario de acción
AZUL_CLARO = "#49A5E6"       # Light Blue — acentos y estados informativos
AQUA = "#2DCCCD"             # Aqua — realces y métricas positivas
VERDE = "#48AE64"            # Éxito
AMBAR = "#F7893B"            # Advertencia
CORAL = "#DA3851"            # Error / riesgo alto
ORO = "#D8BE75"              # Acento premium
GRIS_FONDO = "#F4F6F9"
GRIS_BORDE = "#DDE3EC"
GRIS_TEXTO = "#5A6474"
TEXTO = "#121A2B"
BLANCO = "#FFFFFF"

# Secuencia para series categóricas en Plotly.
SECUENCIA_GRAFICOS = [
    AZUL_MEDIO, AQUA, AZUL_CLARO, ORO, CORAL,
    VERDE, AMBAR, AZUL_NUCLEO, "#8E7CC3", "#00706F",
]

# Escala continua corporativa (claro -> oscuro).
ESCALA_CONTINUA = [
    [0.0, "#E3F2FD"], [0.25, AZUL_CLARO], [0.5, AQUA],
    [0.75, AZUL_MEDIO], [1.0, AZUL_NUCLEO],
]


def plantilla_plotly() -> dict:
    """Layout base para todas las figuras, alineado con la identidad visual."""
    return {
        "font": {"family": "Inter, Segoe UI, Helvetica, Arial, sans-serif",
                 "color": TEXTO, "size": 12},
        "paper_bgcolor": BLANCO,
        "plot_bgcolor": "#FBFCFE",
        "colorway": SECUENCIA_GRAFICOS,
        "title": {"font": {"size": 15, "color": AZUL_NUCLEO}},
        "margin": {"l": 60, "r": 30, "t": 70, "b": 55},
        "xaxis": {"gridcolor": GRIS_BORDE, "zerolinecolor": GRIS_BORDE,
                  "linecolor": GRIS_BORDE},
        "yaxis": {"gridcolor": GRIS_BORDE, "zerolinecolor": GRIS_BORDE,
                  "linecolor": GRIS_BORDE},
        "legend": {"bgcolor": "rgba(255,255,255,0.85)",
                   "bordercolor": GRIS_BORDE, "borderwidth": 1},
    }


CSS = f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');

html, body, [class*="css"], .stApp {{
    font-family: 'Inter', 'Segoe UI', Helvetica, Arial, sans-serif;
}}

.stApp {{ background-color: {GRIS_FONDO}; }}

/* Ancho útil y respiración vertical del contenedor principal */
.block-container {{
    padding-top: 1.6rem;
    padding-bottom: 3rem;
    max-width: 1500px;
}}

/* ---------------------------------------------------- cabecera corporativa */
.bbva-header {{
    background: linear-gradient(115deg, {AZUL_NUCLEO} 0%, #0B3C74 55%, {AZUL_MEDIO} 100%);
    border-radius: 14px;
    padding: 1.5rem 1.9rem;
    margin-bottom: 1.4rem;
    color: {BLANCO};
    box-shadow: 0 8px 26px rgba(7, 33, 70, 0.22);
    position: relative;
    overflow: hidden;
}}
.bbva-header::after {{
    content: "";
    position: absolute; top: -55%; right: -6%;
    width: 320px; height: 320px; border-radius: 50%;
    background: radial-gradient(circle, rgba(45,204,205,0.30) 0%, rgba(45,204,205,0) 70%);
}}
.bbva-header h1 {{
    font-size: 1.72rem; font-weight: 800; margin: 0 0 .3rem 0;
    letter-spacing: -0.02em; color: {BLANCO};
}}
.bbva-header p {{
    margin: 0; font-size: .96rem; color: rgba(255,255,255,.86); max-width: 62ch;
}}
.bbva-marca {{
    display: inline-flex; align-items: center; gap: .55rem;
    font-size: .70rem; font-weight: 700; letter-spacing: .17em;
    text-transform: uppercase; color: {AQUA}; margin-bottom: .5rem;
}}
.bbva-marca::before {{
    content: ""; width: 26px; height: 3px; border-radius: 2px; background: {AQUA};
}}

/* ------------------------------------------------------------ tarjetas KPI */
.kpi-grid {{
    display: grid; grid-template-columns: repeat(auto-fit, minmax(190px, 1fr));
    gap: .85rem; margin: .3rem 0 1.2rem 0;
}}
.kpi {{
    background: {BLANCO}; border: 1px solid {GRIS_BORDE};
    border-left: 4px solid {AZUL_MEDIO};
    border-radius: 11px; padding: .85rem 1.05rem;
    box-shadow: 0 2px 8px rgba(7,33,70,.05);
}}
.kpi .etiqueta {{
    font-size: .70rem; font-weight: 600; letter-spacing: .09em;
    text-transform: uppercase; color: {GRIS_TEXTO}; margin-bottom: .28rem;
}}
.kpi .valor {{
    font-size: 1.52rem; font-weight: 800; color: {AZUL_NUCLEO}; line-height: 1.1;
}}
.kpi .nota {{ font-size: .74rem; color: {GRIS_TEXTO}; margin-top: .18rem; }}
.kpi.aqua {{ border-left-color: {AQUA}; }}
.kpi.exito {{ border-left-color: {VERDE}; }}
.kpi.alerta {{ border-left-color: {AMBAR}; }}
.kpi.riesgo {{ border-left-color: {CORAL}; }}

/* --------------------------------------------------------------- secciones */
.seccion {{
    display: flex; align-items: center; gap: .6rem;
    margin: 1.5rem 0 .8rem 0; padding-bottom: .5rem;
    border-bottom: 2px solid {GRIS_BORDE};
}}
.seccion .indice {{
    background: {AZUL_MEDIO}; color: {BLANCO}; font-weight: 700; font-size: .78rem;
    width: 26px; height: 26px; border-radius: 7px;
    display: flex; align-items: center; justify-content: center; flex-shrink: 0;
}}
.seccion .titulo {{
    font-size: 1.03rem; font-weight: 700; color: {AZUL_NUCLEO}; margin: 0;
}}
.seccion .subtitulo {{
    font-size: .82rem; color: {GRIS_TEXTO}; margin-left: auto; text-align: right;
}}

/* ------------------------------------------------------------------ tabs */
.stTabs [data-baseweb="tab-list"] {{
    gap: .3rem; background: {BLANCO}; padding: .38rem;
    border-radius: 11px; border: 1px solid {GRIS_BORDE};
}}
.stTabs [data-baseweb="tab"] {{
    height: 44px; border-radius: 8px; padding: 0 1.15rem;
    font-weight: 600; font-size: .90rem; color: {GRIS_TEXTO};
    background: transparent;
}}
.stTabs [aria-selected="true"] {{
    background: {AZUL_NUCLEO} !important; color: {BLANCO} !important;
}}
.stTabs [data-baseweb="tab-panel"] {{ padding-top: 1.1rem; }}

/* --------------------------------------------------------------- sidebar */
section[data-testid="stSidebar"] {{
    background: {AZUL_NUCLEO};
    border-right: 1px solid rgba(255,255,255,.09);
}}
section[data-testid="stSidebar"] * {{ color: #E8EEF7 !important; }}
section[data-testid="stSidebar"] h1,
section[data-testid="stSidebar"] h2,
section[data-testid="stSidebar"] h3 {{
    color: {BLANCO} !important; font-weight: 700;
}}
section[data-testid="stSidebar"] .stRadio > label {{
    color: {AQUA} !important; font-weight: 700;
    font-size: .72rem; letter-spacing: .1em; text-transform: uppercase;
}}
section[data-testid="stSidebar"] div[role="radiogroup"] > label {{
    background: rgba(255,255,255,.055); border: 1px solid rgba(255,255,255,.10);
    border-radius: 9px; padding: .58rem .75rem; margin-bottom: .38rem;
    transition: all .16s ease;
}}
section[data-testid="stSidebar"] div[role="radiogroup"] > label:hover {{
    background: rgba(73,165,230,.24); border-color: {AZUL_CLARO};
}}
.barra-lateral-marca {{
    text-align: center; padding: .3rem 0 1rem 0;
    border-bottom: 1px solid rgba(255,255,255,.13); margin-bottom: 1.1rem;
}}
.barra-lateral-marca .logo {{
    font-size: 1.35rem; font-weight: 800; letter-spacing: .13em; color: {BLANCO};
}}
.barra-lateral-marca .sub {{
    font-size: .66rem; letter-spacing: .13em; text-transform: uppercase;
    color: {AQUA} !important;
}}

/* --------------------------------------------------------------- botones */
.stButton > button, .stDownloadButton > button {{
    border-radius: 9px; font-weight: 600; font-size: .89rem;
    padding: .58rem 1.15rem; border: 1px solid transparent; transition: all .16s ease;
}}
.stButton > button[kind="primary"], .stDownloadButton > button {{
    background: {AZUL_MEDIO}; color: {BLANCO}; border-color: {AZUL_MEDIO};
}}
.stButton > button[kind="primary"]:hover, .stDownloadButton > button:hover {{
    background: {AZUL_NUCLEO}; border-color: {AZUL_NUCLEO};
    transform: translateY(-1px); box-shadow: 0 4px 12px rgba(7,33,70,.20);
}}
.stButton > button[kind="secondary"] {{
    background: {BLANCO}; color: {AZUL_MEDIO}; border-color: {AZUL_MEDIO};
}}
.stButton > button[kind="secondary"]:hover {{ background: #EAF3FB; }}

/* ------------------------------------------------------------ formularios */
div[data-testid="stFileUploader"] {{
    background: {BLANCO}; border: 1.5px dashed {GRIS_BORDE};
    border-radius: 11px; padding: .55rem;
}}
div[data-testid="stFileUploader"]:hover {{ border-color: {AZUL_CLARO}; }}

div[data-testid="stExpander"] {{
    background: {BLANCO}; border: 1px solid {GRIS_BORDE};
    border-radius: 11px; overflow: hidden;
}}

/* Tarjeta de acceso */
.tarjeta-login {{
    background: {BLANCO}; border: 1px solid {GRIS_BORDE}; border-radius: 15px;
    padding: 2rem 2.1rem; box-shadow: 0 10px 34px rgba(7,33,70,.10);
}}
.tarjeta-login h3 {{
    margin: 0 0 .25rem 0; color: {AZUL_NUCLEO}; font-size: 1.16rem; font-weight: 700;
}}
.tarjeta-login p {{ color: {GRIS_TEXTO}; font-size: .86rem; margin: 0 0 1.1rem 0; }}

/* Etiquetas de estado */
.pastilla {{
    display: inline-block; padding: .2rem .62rem; border-radius: 20px;
    font-size: .72rem; font-weight: 600; margin-right: .3rem;
}}
.pastilla.ok {{ background: #E6F5EA; color: #1F7A38; }}
.pastilla.no {{ background: #FCE8EC; color: #A32036; }}
.pastilla.info {{ background: #E7F1FB; color: {AZUL_MEDIO}; }}

/* Ocultar cromo por defecto de Streamlit */
#MainMenu, footer {{ visibility: hidden; }}
div[data-testid="stDecoration"] {{ display: none; }}

h1, h2, h3, h4 {{ color: {AZUL_NUCLEO}; font-weight: 700; }}
hr {{ border-color: {GRIS_BORDE}; }}
</style>
"""


def aplicar_estilos() -> None:
    """Inyecta la hoja de estilos corporativa en la pagina."""
    st.markdown(CSS, unsafe_allow_html=True)
