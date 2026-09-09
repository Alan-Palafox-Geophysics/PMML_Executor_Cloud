"""
ui.tabs.tab4_roadmap
====================
Hoja de ruta de los modulos analiticos previstos para el entorno.
"""

from __future__ import annotations

import streamlit as st

from ui import components as comp
from ui.theme import AQUA, AZUL_CLARO, AZUL_MEDIO, AZUL_NUCLEO, GRIS_BORDE, GRIS_TEXTO

MODULOS = [
    {
        "titulo": "Poder discriminante",
        "estado": "En diseño",
        "detalle": "Curva ROC, AUC, Gini y KS por segmento, con intervalos de "
                   "confianza por bootstrap para contrastar el desempeño "
                   "declarado en la documentación del modelo.",
    },
    {
        "titulo": "Estabilidad poblacional",
        "estado": "En diseño",
        "detalle": "PSI y CSI sobre la distribución del score y de cada "
                   "predictor, comparando la ventana de desarrollo con la "
                   "población vigente.",
    },
    {
        "titulo": "Calibración",
        "estado": "Previsto",
        "detalle": "Contraste entre la probabilidad estimada y la tasa "
                   "observada de incumplimiento por bucket, con prueba "
                   "binomial y de Hosmer-Lemeshow.",
    },
    {
        "titulo": "Backtesting temporal",
        "estado": "Previsto",
        "detalle": "Seguimiento del desempeño por cosecha mensual para "
                   "detectar degradación antes de que impacte la decisión.",
    },
    {
        "titulo": "Trazabilidad de ejecuciones",
        "estado": "Previsto",
        "detalle": "Registro de cada corrida con huella del modelo, del "
                   "dataset y del resultado, para reconstruir cualquier "
                   "scoring histórico ante una revisión.",
    },
    {
        "titulo": "Comparación entre versiones",
        "estado": "Previsto",
        "detalle": "Análisis de migración de score y de decisión al sustituir "
                   "un modelo por su nueva versión.",
    },
]


def render() -> None:
    comp.seccion("4.1", "Módulos analíticos en desarrollo",
                 "Validación de modelos de riesgo")

    st.caption(
        "El entorno cubre hoy la ejecución y la conciliación de modelos. "
        "Las siguientes capacidades completan el ciclo de validación."
    )

    tarjetas = []
    for modulo in MODULOS:
        color = AQUA if modulo["estado"] == "En diseño" else AZUL_CLARO
        tarjetas.append(
            f"""
            <div style="background:#FFFFFF;border:1px solid {GRIS_BORDE};
                        border-radius:12px;padding:1.05rem 1.15rem;
                        border-top:3px solid {color};height:100%;">
                <div style="display:flex;align-items:center;gap:.5rem;
                            margin-bottom:.45rem;">
                    <span style="font-weight:700;color:{AZUL_NUCLEO};
                                 font-size:.98rem;">{modulo['titulo']}</span>
                </div>
                <div style="display:inline-block;background:#EEF4FA;color:{AZUL_MEDIO};
                            font-size:.68rem;font-weight:600;padding:.14rem .55rem;
                            border-radius:20px;margin-bottom:.55rem;">
                    {modulo['estado']}
                </div>
                <div style="font-size:.845rem;color:{GRIS_TEXTO};line-height:1.5;">
                    {modulo['detalle']}
                </div>
            </div>
            """
        )

    st.markdown(
        '<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(290px,1fr));'
        f'gap:.9rem;">{"".join(tarjetas)}</div>',
        unsafe_allow_html=True,
    )

    comp.seccion("4.2", "Sugerencias")
    st.info(
        "¿Necesitas un módulo que no aparece aquí? Documenta el requerimiento "
        "con el objetivo analítico, las entradas disponibles y la salida "
        "esperada para incorporarlo a la planificación."
    )
