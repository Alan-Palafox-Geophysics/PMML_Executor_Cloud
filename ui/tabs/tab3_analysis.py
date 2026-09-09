"""
ui.tabs.tab3_analysis
=====================
Analisis de desviaciones entre el scoring de Python (PMML) y el de la
plataforma de decision.

Correcciones metodologicas respecto de la version anterior:

  * **Error relativo estable.** Antes se calculaba (py - pwc) / (py + 1e-9).
    Cuando la probabilidad de Python es cercana a cero —lo habitual en la cola
    buena de una cartera— el denominador colapsa y el error se dispara a
    millones de por ciento, contaminando la escala del grafico y ocultando las
    desviaciones reales. Ahora se usa la diferencia absoluta como metrica
    principal y el error relativo se calcula solo sobre registros con
    denominador significativo.
  * **Criterio de tolerancia explicito.** Se declara un umbral de equivalencia
    y se reporta cuantos registros lo superan, que es la pregunta que responde
    una validacion de implantacion.
  * **Robustez ante nulos.** Se descartan filas sin par antes de calcular, en
    lugar de propagar NaN hasta los limites de los ejes.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from core.data_utils import detectar_columnas_probabilidad
from ui import components as comp
from ui.theme import (
    AQUA,
    AZUL_MEDIO,
    AZUL_NUCLEO,
    CORAL,
    ESCALA_CONTINUA,
    SECUENCIA_GRAFICOS,
    VERDE,
    plantilla_plotly,
)


def _aplicar_estilo(figura):
    figura.update_layout(**plantilla_plotly())
    return figura


def _metricas(serie_a: pd.Series, serie_b: pd.Series, tolerancia: float) -> dict:
    """Estadisticos de concordancia entre dos vectores de probabilidad."""
    diferencia = serie_a - serie_b
    absoluta = diferencia.abs()

    # El error relativo solo es interpretable con denominador no despreciable.
    significativos = serie_b.abs() > 1e-6
    relativo = pd.Series(np.nan, index=serie_a.index, dtype="float64")
    relativo.loc[significativos] = (
        100.0 * diferencia.loc[significativos] / serie_b.loc[significativos]
    )

    fuera = int((absoluta > tolerancia).sum())
    correlacion = serie_a.corr(serie_b) if len(serie_a) > 1 else np.nan

    return {
        "n": len(serie_a),
        "dif_media": float(diferencia.mean()),
        "dif_abs_media": float(absoluta.mean()),
        "dif_abs_max": float(absoluta.max()),
        "rmse": float(np.sqrt((diferencia ** 2).mean())),
        "p99_abs": float(absoluta.quantile(0.99)),
        "fuera_tolerancia": fuera,
        "pct_fuera": 100.0 * fuera / max(len(serie_a), 1),
        "correlacion": float(correlacion) if pd.notna(correlacion) else np.nan,
        "error_relativo": relativo,
        "diferencia": diferencia,
        "absoluta": absoluta,
    }


def render() -> None:
    consolidado = st.session_state.get("matriz_consolidada")

    if consolidado is None:
        comp.vacio(
            "Aún no hay una matriz consolidada en la sesión. "
            "Ejecuta la conciliación en la pestaña anterior.",
            icono="◇",
        )
        return

    df = consolidado.copy()

    columnas_python = detectar_columnas_probabilidad(df)
    columnas_pwc = detectar_columnas_probabilidad(df, prefijo="pwc_")
    columnas_control = detectar_columnas_probabilidad(df, prefijo="cc_")

    if not columnas_python or not columnas_pwc:
        st.error(
            "No se identificaron columnas comparables de probabilidad o score. "
            "Se buscan nombres que contengan «probability», «score», «puntaje» "
            "o «pd_» en ambos orígenes."
        )
        return

    comp.seccion("3.1", "Selección de variables a comparar")

    col_a, col_b, col_c = st.columns(3)
    with col_a:
        columna_py = st.selectbox("Probabilidad — Python (PMML)", columnas_python)
    with col_b:
        columna_pwc = st.selectbox("Probabilidad — Power Curve", columnas_pwc)
    with col_c:
        opciones_segmento = ["(sin segmentación)"] + [
            c for c in df.columns
            if df[c].nunique(dropna=True) <= 200 and c not in (columna_py, columna_pwc)
        ]
        columna_segmento = st.selectbox("Segmentar por", opciones_segmento)

    tolerancia = st.select_slider(
        "Tolerancia de equivalencia (diferencia absoluta admitida)",
        options=[1e-9, 1e-8, 1e-7, 1e-6, 1e-5, 1e-4, 1e-3, 1e-2],
        value=1e-6,
        format_func=lambda v: f"{v:.0e}",
        help="Umbral por debajo del cual ambos motores se consideran "
             "equivalentes para efectos de validación de implantación.",
    )

    # ------------------------------------------------------------ preparación
    df[columna_py] = pd.to_numeric(df[columna_py], errors="coerce")
    df[columna_pwc] = pd.to_numeric(df[columna_pwc], errors="coerce")

    validos = df[[columna_py, columna_pwc]].notna().all(axis=1)
    descartados = int((~validos).sum())
    trabajo = df.loc[validos].copy()

    if trabajo.empty:
        st.error(
            "No hay registros con valor en ambas columnas. Revisa la tasa de "
            "emparejamiento de la conciliación."
        )
        return

    resultado = _metricas(trabajo[columna_py], trabajo[columna_pwc], tolerancia)
    trabajo["diferencia"] = resultado["diferencia"]
    trabajo["diferencia_absoluta"] = resultado["absoluta"]
    trabajo["error_relativo_pct"] = resultado["error_relativo"]

    # --------------------------------------------------------------- veredicto
    comp.seccion("3.2", "Resultado de la validación",
                 f"{descartados:,} registro(s) sin par excluido(s)")

    equivalente = resultado["fuera_tolerancia"] == 0
    if equivalente:
        st.success(
            f"**Motores equivalentes.** Los {resultado['n']:,} registros "
            f"comparados presentan diferencias inferiores a {tolerancia:.0e}. "
            "La implantación reproduce el modelo de referencia."
        )
    else:
        st.warning(
            f"**Se detectaron desviaciones.** {resultado['fuera_tolerancia']:,} "
            f"registros ({resultado['pct_fuera']:.2f}%) superan la tolerancia de "
            f"{tolerancia:.0e}. La diferencia absoluta máxima es "
            f"{resultado['dif_abs_max']:.3e}."
        )

    comp.kpis([
        {"etiqueta": "Registros comparados", "valor": f"{resultado['n']:,}"},
        {"etiqueta": "Dif. absoluta media", "valor": f"{resultado['dif_abs_media']:.3e}",
         "nota": "Sesgo medio en magnitud", "estilo": "aqua"},
        {"etiqueta": "Dif. absoluta máxima", "valor": f"{resultado['dif_abs_max']:.3e}",
         "nota": "Peor caso",
         "estilo": "exito" if equivalente else "riesgo"},
        {"etiqueta": "RMSE", "valor": f"{resultado['rmse']:.3e}",
         "nota": "Error cuadrático medio"},
        {"etiqueta": "Fuera de tolerancia", "valor": f"{resultado['fuera_tolerancia']:,}",
         "nota": f"{resultado['pct_fuera']:.2f}% del total",
         "estilo": "exito" if equivalente else "alerta"},
        {"etiqueta": "Correlación", "valor": f"{resultado['correlacion']:.6f}"
         if pd.notna(resultado["correlacion"]) else "—",
         "nota": "Pearson"},
    ])

    # ----------------------------------------------------------- segmentación
    color = None
    escala_continua = None
    secuencia = [AZUL_MEDIO]

    if columna_segmento != "(sin segmentación)":
        unicos = trabajo[columna_segmento].nunique(dropna=True)
        if unicos <= 40:
            color = f"_seg_{columna_segmento}"
            trabajo[color] = trabajo[columna_segmento].astype(str)
            secuencia = (
                SECUENCIA_GRAFICOS if unicos <= len(SECUENCIA_GRAFICOS)
                else px.colors.sample_colorscale(
                    "turbo", [i / max(unicos - 1, 1) for i in range(unicos)]
                )
            )
        else:
            color = columna_segmento
            escala_continua = ESCALA_CONTINUA
            secuencia = None

    etiquetas = {
        columna_py: "Python (PMML)",
        columna_pwc: "Power Curve",
        "diferencia": "Diferencia (Python − Power Curve)",
        "diferencia_absoluta": "Diferencia absoluta",
        "error_relativo_pct": "Error relativo (%)",
    }

    # -------------------------------------------------------------- gráficos
    comp.seccion("3.3", "Diagnóstico gráfico")

    col_g1, col_g2 = st.columns(2)

    with col_g1:
        st.markdown("**Concordancia entre motores**")
        figura = px.scatter(
            trabajo, x=columna_py, y=columna_pwc, color=color,
            labels=etiquetas, opacity=0.65,
            color_discrete_sequence=secuencia,
            color_continuous_scale=escala_continua,
            title="Dispersión frente a la recta de identidad",
        )
        minimo = float(min(trabajo[columna_py].min(), trabajo[columna_pwc].min()))
        maximo = float(max(trabajo[columna_py].max(), trabajo[columna_pwc].max()))
        figura.add_trace(
            go.Scatter(
                x=[minimo, maximo], y=[minimo, maximo], mode="lines",
                name="Identidad (y = x)",
                line=dict(dash="dash", color=AZUL_NUCLEO, width=1.6),
            )
        )
        st.plotly_chart(_aplicar_estilo(figura), use_container_width=True)

    with col_g2:
        st.markdown("**Estructura del residuo**")
        figura_residuo = px.scatter(
            trabajo, x=columna_py, y="diferencia", color=color,
            labels=etiquetas, opacity=0.65,
            color_discrete_sequence=secuencia,
            color_continuous_scale=escala_continua,
            title="Diferencia absoluta frente al nivel de probabilidad",
        )
        figura_residuo.add_hline(y=0, line_dash="dash", line_color=AZUL_NUCLEO)
        figura_residuo.add_hline(y=tolerancia, line_dash="dot", line_color=CORAL,
                                 annotation_text="Tolerancia")
        figura_residuo.add_hline(y=-tolerancia, line_dash="dot", line_color=CORAL)
        st.plotly_chart(_aplicar_estilo(figura_residuo), use_container_width=True)

    col_g3, col_g4 = st.columns(2)

    with col_g3:
        st.markdown("**Distribución de las diferencias**")
        figura_hist = px.histogram(
            trabajo, x="diferencia", nbins=60, labels=etiquetas,
            color_discrete_sequence=[AZUL_MEDIO],
            title="Histograma del residuo",
        )
        st.plotly_chart(_aplicar_estilo(figura_hist), use_container_width=True)

    with col_g4:
        st.markdown("**Distribución de ambos motores**")
        figura_dist = go.Figure()
        figura_dist.add_trace(go.Histogram(
            x=trabajo[columna_py], name="Python (PMML)",
            marker_color=AZUL_MEDIO, opacity=0.62, nbinsx=50))
        figura_dist.add_trace(go.Histogram(
            x=trabajo[columna_pwc], name="Power Curve",
            marker_color=AQUA, opacity=0.62, nbinsx=50))
        figura_dist.update_layout(barmode="overlay",
                                  title="Comparación de distribuciones")
        st.plotly_chart(_aplicar_estilo(figura_dist), use_container_width=True)

    # ------------------------------------------------- detalle por segmento
    if columna_segmento != "(sin segmentación)":
        comp.seccion("3.4", "Desglose por segmento")
        agregado = (
            trabajo.groupby(trabajo[columna_segmento].astype(str))
            .agg(
                Registros=("diferencia_absoluta", "size"),
                Dif_media=("diferencia", "mean"),
                Dif_abs_media=("diferencia_absoluta", "mean"),
                Dif_abs_max=("diferencia_absoluta", "max"),
            )
            .reset_index()
            .rename(columns={
                columna_segmento: "Segmento",
                "Dif_media": "Diferencia media",
                "Dif_abs_media": "Dif. absoluta media",
                "Dif_abs_max": "Dif. absoluta máxima",
            })
        )
        agregado["Fuera de tolerancia"] = (
            trabajo.assign(_s=trabajo[columna_segmento].astype(str))
            .groupby("_s")["diferencia_absoluta"]
            .apply(lambda s: int((s > tolerancia).sum()))
            .values
        )
        comp.tabla(agregado)

    # -------------------------------------------- registros con mayor desvío
    comp.seccion("3.5", "Registros con mayor desviación")
    columnas_detalle = [c for c in [
        st.session_state.get("llave_consolidada"), columna_py, columna_pwc,
        "diferencia", "diferencia_absoluta", "error_relativo_pct",
    ] if c and c in trabajo.columns]

    peores = trabajo.nlargest(min(100, len(trabajo)), "diferencia_absoluta")
    comp.tabla(peores[columnas_detalle].head(100), altura=340, ocultar_indice=False)

    comp.seccion("3.6", "Exportación del análisis")
    columnas_export = columnas_detalle + (
        [columna_segmento] if columna_segmento != "(sin segmentación)" else []
    )
    comp.descargas(trabajo[columnas_export], "analisis_desviaciones",
                   clave="analisis")

    # ---------------------------------------------- comparación con control
    if columnas_control:
        comp.seccion("3.7", "Contraste con cifras de control")
        columna_cc = st.selectbox("Probabilidad — cifras de control", columnas_control)
        trabajo[columna_cc] = pd.to_numeric(trabajo[columna_cc], errors="coerce")

        validos_cc = trabajo[[columna_cc, columna_pwc]].notna().all(axis=1)
        if not validos_cc.any():
            comp.vacio("No hay registros comparables con las cifras de control.")
            return

        sub = trabajo.loc[validos_cc]
        control = _metricas(sub[columna_cc], sub[columna_pwc], tolerancia)

        comp.kpis([
            {"etiqueta": "Registros", "valor": f"{control['n']:,}"},
            {"etiqueta": "Dif. absoluta media", "valor": f"{control['dif_abs_media']:.3e}",
             "estilo": "aqua"},
            {"etiqueta": "Dif. absoluta máxima", "valor": f"{control['dif_abs_max']:.3e}",
             "estilo": "exito" if control["fuera_tolerancia"] == 0 else "riesgo"},
            {"etiqueta": "Fuera de tolerancia", "valor": f"{control['fuera_tolerancia']:,}",
             "nota": f"{control['pct_fuera']:.2f}%"},
        ])

        figura_cc = px.scatter(
            sub, x=columna_cc, y=columna_pwc, opacity=0.65,
            color_discrete_sequence=[VERDE],
            labels={columna_cc: "Cifras de control", columna_pwc: "Power Curve"},
            title="Cifras de control frente a Power Curve",
        )
        minimo = float(min(sub[columna_cc].min(), sub[columna_pwc].min()))
        maximo = float(max(sub[columna_cc].max(), sub[columna_pwc].max()))
        figura_cc.add_trace(go.Scatter(
            x=[minimo, maximo], y=[minimo, maximo], mode="lines",
            name="Identidad (y = x)",
            line=dict(dash="dash", color=AZUL_NUCLEO, width=1.6)))
        st.plotly_chart(_aplicar_estilo(figura_cc), use_container_width=True)
