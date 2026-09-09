"""
ui.tabs.tab1_execution
======================
Modulos de auditoria de modelos y ejecucion de scoring.

  1.1  Auditoría de metadatos — radiografía estática del PMML.
  1.2  Scoring de modelo único — un PMML sobre un dataset.
  1.3  Scoring multimodelo     — enrutamiento por segmento.

Todo el manejo de archivos se hace en memoria (bytes). La version anterior
escribia temporales en el directorio de trabajo con el nombre del archivo
subido, lo que en un entorno multiusuario provoca colisiones entre sesiones y
deja residuos si la ejecucion falla.
"""

from __future__ import annotations

import base64
import json
import zlib

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

from core import jvm
from core.data_utils import (
    a_csv_bytes,
    leer_diccionario_tipos,
    leer_tabla,
    perfilar_dataframe,
)
from core.metadata import analizar_pmml, construir_mermaid
from core.pmml_engine import (
    ErrorEsquemaPMML,
    describir_campos,
    ejecutar_modelo_unico,
    ejecutar_multimodelo,
)
from ui import components as comp
from ui.theme import AZUL_NUCLEO


# --------------------------------------------------------------------------
# Cache de evaluadores
# --------------------------------------------------------------------------
@st.cache_resource(show_spinner=False, max_entries=3)
def _evaluador_cacheado(huella: str, contenido: bytes):
    """
    Construye el evaluador una sola vez por modelo.

    La clave es el hash del contenido, de modo que volver a subir el mismo
    archivo reutiliza el evaluador ya inicializado en la JVM. Sin esta caché,
    cada interacción de Streamlit reconstruiría el modelo desde cero.

    `max_entries` es deliberadamente bajo: cada evaluador retiene su modelo
    completo en el heap de la JVM, y un ensamble grande puede ocupar cientos de
    megabytes. Cachear muchos modelos a la vez agota el heap y provoca
    `OutOfMemoryError` incluso antes de empezar a puntuar.
    """
    return jvm.construir_evaluador(contenido)


def liberar_cache_modelos() -> None:
    """Vacía la caché de evaluadores y fuerza la recolección en la JVM."""
    _evaluador_cacheado.clear()
    jvm.liberar_memoria_java()


def obtener_evaluador(contenido: bytes):
    return _evaluador_cacheado(jvm.hash_contenido(contenido), contenido)


def _tabla_markdown(df: pd.DataFrame) -> str:
    if df is None or df.empty:
        return "_Sin registros._\n\n"
    columnas = df.columns.tolist()
    lineas = ["| " + " | ".join(map(str, columnas)) + " |",
              "| " + " | ".join(["---"] * len(columnas)) + " |"]
    for _, fila in df.iterrows():
        lineas.append("| " + " | ".join(str(v) for v in fila.values) + " |")
    return "\n".join(lineas) + "\n\n"


# --------------------------------------------------------------------------
# 1.1 Auditoría de metadatos
# --------------------------------------------------------------------------
def _modulo_metadata() -> None:
    comp.seccion("1.1", "Auditoría de metadatos y arquitectura del modelo",
                 "Análisis estático — no requiere ejecución")

    st.caption(
        "Extrae la ficha técnica, el esquema de variables, las transformaciones "
        "y la topología interna del modelo directamente del archivo PMML."
    )

    archivo = st.file_uploader(
        "Archivo del modelo (.pmml / .xml)", type=["pmml", "xml"], key="meta_archivo"
    )

    if archivo is None:
        comp.vacio("Carga un archivo PMML para generar la auditoría del modelo.")
        return

    if not st.button("Analizar modelo", type="primary", key="btn_meta"):
        return

    with st.spinner("Parseando estructura del modelo..."):
        metadatos = analizar_pmml(archivo.getvalue())

    if metadatos.error:
        st.error(metadatos.error)
        return

    st.success("Estructura del modelo interpretada correctamente.")

    comp.kpis([
        {"etiqueta": "Predictores", "valor": len(metadatos.entradas),
         "nota": "Variables activas"},
        {"etiqueta": "Salidas", "valor": len(metadatos.salidas),
         "nota": "Campos calculados", "estilo": "aqua"},
        {"etiqueta": "Transformaciones", "valor": len(metadatos.transformaciones),
         "nota": "Variables derivadas"},
        {"etiqueta": "Capas de modelo", "valor": len(metadatos.arquitectura),
         "nota": "Niveles de arquitectura", "estilo": "exito"},
    ])

    comp.seccion("A", "Ficha técnica")
    ficha = pd.DataFrame(
        [{"Atributo": k, "Valor": v} for k, v in metadatos.ficha.items()]
    )
    comp.tabla(ficha)

    comp.seccion("B", "Esquema de variables")
    col_a, col_b = st.columns(2)
    with col_a:
        st.markdown("**Variables de entrada**")
        comp.tabla(pd.DataFrame(metadatos.entradas), altura=310)
    with col_b:
        st.markdown("**Variables objetivo y de salida**")
        if metadatos.objetivos:
            comp.tabla(pd.DataFrame(metadatos.objetivos))
        comp.tabla(pd.DataFrame(metadatos.salidas), altura=210)

    if metadatos.transformaciones:
        comp.seccion("C", "Transformaciones declaradas")
        comp.tabla(pd.DataFrame(metadatos.transformaciones), altura=250)

    comp.seccion("D", "Arquitectura del modelo")
    codigo_mermaid = construir_mermaid(metadatos)
    _renderizar_diagrama(codigo_mermaid)
    comp.tabla(pd.DataFrame(metadatos.arquitectura))

    comp.seccion("E", "Exportación de la documentación")
    texto_md = _documento_markdown(archivo.name, metadatos, codigo_mermaid)

    col_1, col_2 = st.columns(2)
    with col_1:
        st.download_button(
            "Descargar log de auditoría (.txt)",
            data=metadatos.log.encode("utf-8"),
            file_name=f"auditoria_{archivo.name}.txt",
            mime="text/plain",
            use_container_width=True,
        )
    with col_2:
        st.download_button(
            "Descargar documentación (.md)",
            data=texto_md.encode("utf-8"),
            file_name=f"documentacion_{archivo.name}.md",
            mime="text/markdown",
            use_container_width=True,
        )

    with st.expander("Vista previa de la documentación", expanded=False):
        st.markdown(texto_md)


def _renderizar_diagrama(codigo_mermaid: str) -> None:
    """Renderiza el diagrama Mermaid con opción de descarga en SVG."""
    html = f"""
    <!DOCTYPE html><html><head>
    <script type="module">
      import mermaid from 'https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.esm.min.mjs';
      mermaid.initialize({{ startOnLoad: true, theme: 'base', securityLevel: 'loose',
        themeVariables: {{ fontFamily: 'Inter, Segoe UI, sans-serif',
                           primaryColor: '#1464A5', lineColor: '#5A6474' }} }});
      window.descargarSVG = function() {{
        const svg = document.querySelector('.mermaid svg');
        if (!svg) return;
        svg.style.backgroundColor = 'white';
        const fuente = new XMLSerializer().serializeToString(svg);
        const url = URL.createObjectURL(new Blob([fuente], {{type: "image/svg+xml;charset=utf-8"}}));
        const a = document.createElement("a");
        a.href = url; a.download = "arquitectura_modelo.svg";
        document.body.appendChild(a); a.click(); document.body.removeChild(a);
        URL.revokeObjectURL(url);
      }};
    </script>
    <style>
      body {{ background: transparent; margin: 0;
             font-family: Inter, 'Segoe UI', sans-serif; }}
      .btn {{ display:block; margin: 4px auto 14px auto; padding: 9px 20px;
              background: #1464A5; color: #fff; border: none; border-radius: 8px;
              font-weight: 600; font-size: 13px; cursor: pointer; }}
      .btn:hover {{ background: {AZUL_NUCLEO}; }}
      .mermaid {{ display:flex; justify-content:center; }}
    </style></head>
    <body>
      <button class="btn" onclick="window.descargarSVG()">Descargar diagrama (SVG)</button>
      <div class="mermaid">
{codigo_mermaid}
      </div>
    </body></html>
    """
    altura = min(300 + 78 * max(len(codigo_mermaid.splitlines()) - 8, 0), 900)
    components.html(html, height=altura, scrolling=True)


def _documento_markdown(nombre, metadatos, codigo_mermaid: str) -> str:
    """Arma la documentación exportable del modelo."""
    texto = f"# Documentación de modelo — {nombre}\n\n"
    texto += "## 1. Ficha técnica\n\n"
    for clave, valor in metadatos.ficha.items():
        texto += f"- **{clave}:** {valor}\n"

    texto += "\n## 2. Variables de entrada\n\n"
    texto += _tabla_markdown(pd.DataFrame(metadatos.entradas))
    texto += "## 3. Variables objetivo\n\n"
    texto += _tabla_markdown(pd.DataFrame(metadatos.objetivos))
    texto += "## 4. Variables de salida\n\n"
    texto += _tabla_markdown(pd.DataFrame(metadatos.salidas))
    texto += "## 5. Transformaciones\n\n"
    texto += _tabla_markdown(pd.DataFrame(metadatos.transformaciones))
    texto += "## 6. Arquitectura\n\n"

    # Kroki renderiza el diagrama en cualquier visor de Markdown.
    limpio = codigo_mermaid.replace("<br/>", " ")
    comprimido = zlib.compress(limpio.encode("utf-8"), 9)
    clave = base64.urlsafe_b64encode(comprimido).decode("utf-8")
    texto += f"![Arquitectura del modelo](https://kroki.io/mermaid/svg/{clave})\n\n"
    texto += _tabla_markdown(pd.DataFrame(metadatos.arquitectura))

    texto += "```mermaid\n" + limpio + "\n```\n"
    return texto


# --------------------------------------------------------------------------
# 1.2 Scoring de modelo único
# --------------------------------------------------------------------------
def _modulo_scoring_unico(estado_jvm, usuario) -> None:
    comp.seccion("1.2", "Scoring con modelo único",
                 "Evaluación de un PMML sobre un dataset")

    if not estado_jvm.disponible:
        comp.estado_motor(estado_jvm, mostrar_diagnostico=usuario.puede("diagnostico"))
        return

    if usuario.puede("diagnostico"):
        comp.estado_motor(estado_jvm, mostrar_diagnostico=True)

    col_a, col_b = st.columns(2)
    with col_a:
        archivo_pmml = st.file_uploader("Modelo (.pmml)", type=["pmml", "xml"],
                                        key="unico_pmml")
    with col_b:
        archivo_datos = st.file_uploader("Dataset (.csv / .parquet)",
                                         type=["csv", "parquet"], key="unico_datos")

    with st.expander("Opciones avanzadas", expanded=False):
        col_c, col_d = st.columns(2)
        with col_c:
            archivo_tipos = st.file_uploader(
                "Diccionario de tipos (opcional)", type=["csv"], key="unico_tipos",
                help="Dos columnas: nombre de variable y tipo. Sustituye al "
                     "esquema declarado en el PMML.",
            )
        with col_d:
            tamano_bloque = st.number_input(
                "Tamaño de bloque", min_value=500, max_value=100_000,
                value=1_000, step=500,
                help="Registros enviados por lote a la JVM. Bloques menores "
                     "reducen el consumo de memoria.",
            )

    listo = archivo_pmml is not None and archivo_datos is not None
    if not listo:
        comp.vacio("Carga el modelo y el dataset para habilitar la ejecución.")
        return

    if not st.button("Ejecutar scoring", type="primary", key="btn_unico"):
        _mostrar_persistido("unico")
        return

    barra = st.progress(0.0, text="Preparando ejecución...")
    try:
        barra.progress(0.10, text="Inicializando el evaluador del modelo...")
        evaluador = obtener_evaluador(archivo_pmml.getvalue())

        barra.progress(0.25, text="Leyendo el dataset...")
        df_crudo = leer_tabla(archivo_datos.getvalue(), nombre=archivo_datos.name)

        esquema_externo = None
        if archivo_tipos is not None:
            esquema_externo = leer_diccionario_tipos(
                archivo_tipos.getvalue(), nombre=archivo_tipos.name
            )

        def avance(hechas: int, total: int) -> None:
            proporcion = 0.35 + 0.6 * (hechas / max(total, 1))
            barra.progress(min(proporcion, 0.95),
                           text=f"Evaluando {hechas:,} de {total:,} registros...")

        barra.progress(0.35, text="Aplicando tipos y validando esquema...")
        resultado = ejecutar_modelo_unico(
            evaluador, df_crudo, esquema_externo=esquema_externo,
            tamano_bloque=int(tamano_bloque), callback_progreso=avance,
        )
        barra.progress(1.0, text="Ejecución finalizada.")

    except ErrorEsquemaPMML as exc:
        barra.empty()
        st.error(str(exc))
        return
    except Exception as exc:
        barra.empty()
        st.error(f"La ejecución no pudo completarse.\n\n**Detalle:** {exc}")
        return

    barra.empty()
    st.session_state.resultado_scoring = resultado.datos
    _guardar_resultado("unico", resultado, "scoring_unico", archivo_pmml.name)
    _mostrar_resultado(resultado, "scoring_unico", archivo_pmml.name)


# --------------------------------------------------------------------------
# 1.3 Scoring multimodelo
# --------------------------------------------------------------------------
def _modulo_scoring_multiple(estado_jvm, usuario) -> None:
    comp.seccion("1.3", "Scoring multimodelo por segmento",
                 "Enrutamiento de registros a modelos especializados")

    if not estado_jvm.disponible:
        comp.estado_motor(estado_jvm, mostrar_diagnostico=usuario.puede("diagnostico"))
        return

    st.caption(
        "Carga un JSON de configuración con la llave `pmml_files`, que asocia "
        "cada segmento con el archivo de modelo que le corresponde."
    )

    with st.expander("Formato esperado del archivo de configuración", expanded=False):
        st.code(
            json.dumps(
                {"pmml_files": {"SEGMENTO_A": "modelo_a.pmml",
                                "SEGMENTO_B": "modelo_b.pmml"}},
                indent=2, ensure_ascii=False,
            ),
            language="json",
        )

    archivo_json = st.file_uploader("Configuración de segmentos (.json)",
                                    type=["json"], key="multi_json")

    mapeo: dict[str, str] = {}
    if archivo_json is not None:
        try:
            configuracion = json.loads(archivo_json.getvalue().decode("utf-8"))
            mapeo = configuracion.get("pmml_files", {})
            if not isinstance(mapeo, dict) or not mapeo:
                st.error("El JSON debe contener la llave `pmml_files` con al "
                         "menos un par segmento → archivo.")
                mapeo = {}
        except json.JSONDecodeError as exc:
            st.error(f"El archivo JSON no es válido: {exc}")

    modelos_cargados: dict[str, object] = {}
    if mapeo:
        comp.seccion("A", "Carga de modelos por segmento",
                     f"{len(mapeo)} modelo(s) requerido(s)")
        for segmento, nombre_archivo in mapeo.items():
            subido = st.file_uploader(
                f"Segmento «{segmento}» → archivo esperado: {nombre_archivo}",
                type=["pmml", "xml"], key=f"multi_pmml_{segmento}",
            )
            if subido is not None:
                modelos_cargados[str(segmento)] = subido

    comp.seccion("B", "Dataset y enrutamiento")
    archivo_datos = st.file_uploader("Dataset a evaluar (.csv / .parquet)",
                                     type=["csv", "parquet"], key="multi_datos")

    variable_segmento = ""
    if archivo_datos is not None:
        try:
            encabezado = leer_tabla(archivo_datos.getvalue(),
                                    nombre=archivo_datos.name).columns.tolist()
            variable_segmento = st.selectbox(
                "Variable de enrutamiento (columna de segmento)",
                options=encabezado,
                help="Columna cuyo valor determina qué modelo evalúa cada registro.",
            )
        except Exception as exc:
            st.error(f"No fue posible leer el dataset: {exc}")

    with st.expander("Opciones avanzadas", expanded=False):
        tamano_bloque = st.number_input(
            "Tamaño de bloque", min_value=500, max_value=100_000,
            value=1_000, step=500, key="multi_bloque",
        )

    completo = bool(mapeo) and len(modelos_cargados) == len(mapeo)
    listo = completo and archivo_datos is not None and bool(variable_segmento)

    if mapeo and not completo:
        faltan = [s for s in mapeo if s not in modelos_cargados]
        st.info("Faltan los modelos de: " + ", ".join(map(str, faltan)))

    if not listo:
        comp.vacio("Completa la configuración, los modelos y el dataset "
                   "para habilitar la ejecución.")
        return

    if not st.button("Ejecutar scoring multimodelo", type="primary", key="btn_multi"):
        _mostrar_persistido("multi")
        return

    barra = st.progress(0.0, text="Preparando ejecución...")
    try:
        barra.progress(0.10, text="Inicializando evaluadores...")
        evaluadores = {
            segmento: obtener_evaluador(archivo.getvalue())
            for segmento, archivo in modelos_cargados.items()
        }

        barra.progress(0.30, text="Leyendo el dataset...")
        df_crudo = leer_tabla(archivo_datos.getvalue(), nombre=archivo_datos.name)

        def avance(segmento: str, indice: int, total: int) -> None:
            barra.progress(
                min(0.35 + 0.6 * (indice / max(total, 1)), 0.95),
                text=f"Evaluando segmento «{segmento}» ({indice}/{total})...",
            )

        resultado = ejecutar_multimodelo(
            df_crudo, variable_segmento, evaluadores,
            tamano_bloque=int(tamano_bloque), callback_progreso=avance,
        )
        barra.progress(1.0, text="Ejecución finalizada.")

    except ErrorEsquemaPMML as exc:
        barra.empty()
        st.error(str(exc))
        return
    except Exception as exc:
        barra.empty()
        st.error(f"La ejecución no pudo completarse.\n\n**Detalle:** {exc}")
        return

    barra.empty()
    st.session_state.resultado_scoring = resultado.datos

    if resultado.resumen_segmentos is not None:
        sin_modelo = resultado.resumen_segmentos["Segmento"].astype(str).str.contains(
            "SIN MODELO"
        )
        if sin_modelo.any():
            st.warning(
                "Hay segmentos presentes en el dataset sin modelo asignado. "
                "Esos registros **no fueron evaluados**."
            )

    _guardar_resultado("multi", resultado, "scoring_multimodelo", "multimodelo")
    _mostrar_resultado(resultado, "scoring_multimodelo", "multimodelo")

    if resultado.resumen_segmentos is not None:
        comp.seccion("C", "Distribución por segmento")
        comp.tabla(resultado.resumen_segmentos)


# --------------------------------------------------------------------------
# Presentación de resultados
# --------------------------------------------------------------------------
def _guardar_resultado(cual: str, resultado, nombre_base: str, referencia: str) -> None:
    """
    Conserva la corrida en la sesion y descarta exportaciones anteriores.

    Sin esto, el bloque de resultados solo existia mientras duraba la
    re-ejecucion provocada por el boton «Ejecutar». En cuanto el usuario
    pulsaba cualquier otro control —preparar el CSV, por ejemplo— Streamlit
    volvia a correr el script, el boton de ejecucion ya valia False y toda la
    seccion desaparecia, botones de descarga incluidos.

    Ademas se limpian los archivos ya serializados: si no, una corrida nueva
    seguiria ofreciendo para descarga los bytes de la anterior.
    """
    comp.limpiar_exportaciones()
    st.session_state[f"_resultado_{cual}"] = (resultado, nombre_base, referencia)


def _mostrar_persistido(cual: str) -> None:
    """Vuelve a dibujar la ultima corrida guardada, si la hay."""
    guardado = st.session_state.get(f"_resultado_{cual}")
    if guardado is not None:
        _mostrar_resultado(*guardado)


def _mostrar_resultado(resultado, nombre_base: str, referencia: str) -> None:
    st.success(f"Scoring completado sobre {resultado.filas_procesadas:,} registros.")

    tarjetas = [
        {"etiqueta": "Registros evaluados", "valor": f"{resultado.filas_procesadas:,}",
         "nota": "Filas puntuadas"},
        {"etiqueta": "Variables de entrada", "valor": len(resultado.campos_entrada),
         "nota": "Exigidas por el modelo", "estilo": "aqua"},
        {"etiqueta": "Campos de salida", "valor": len(resultado.campos_salida),
         "nota": "Generados por el modelo"},
    ]
    if resultado.filas_sin_score:
        proporcion = 100.0 * resultado.filas_sin_score / max(resultado.filas_procesadas, 1)
        tarjetas.append({
            "etiqueta": "Registros sin score", "valor": f"{resultado.filas_sin_score:,}",
            "nota": f"{proporcion:.2f}% del total", "estilo": "riesgo",
        })
    if resultado.filas_con_error:
        tarjetas.append({
            "etiqueta": "Filas con error", "valor": f"{resultado.filas_con_error:,}",
            "nota": "Revisar columna «errors»", "estilo": "riesgo",
        })
    comp.kpis(tarjetas)

    if resultado.filas_sin_score:
        st.warning(
            f"**{resultado.filas_sin_score:,} registro(s) no obtuvieron ningún "
            "valor de salida.** Suele deberse a predictores nulos en modelos sin "
            "estrategia de imputación declarada. Estos registros salen del "
            "proceso sin decisión: conviene identificarlos antes de dar el "
            "scoring por cerrado."
        )

    comp.aviso_calidad(resultado.reporte_casteo)

    pestanas = st.tabs(["Resultados", "Perfil de datos", "Estadísticos de salida"])

    with pestanas[0]:
        comp.tabla(resultado.datos.head(500), altura=430, ocultar_indice=False)
        st.caption(
            f"Vista previa de las primeras 500 filas de "
            f"{resultado.filas_procesadas:,}. La descarga incluye el total."
        )
        comp.descargas(resultado.datos, nombre_base, clave=referencia)

    with pestanas[1]:
        comp.tabla(perfilar_dataframe(resultado.datos), altura=380)

    with pestanas[2]:
        numericas = resultado.datos.select_dtypes(include="number")
        salidas = [c for c in resultado.campos_salida if c in numericas.columns]
        objetivo = numericas[salidas] if salidas else numericas
        if objetivo.empty:
            comp.vacio("El modelo no produjo salidas numéricas resumibles.")
        else:
            comp.tabla(objetivo.describe().T.reset_index()
                       .rename(columns={"index": "Variable"}))


# --------------------------------------------------------------------------
def render(submodulo: str, estado_jvm, usuario) -> None:
    if submodulo.startswith("1.1"):
        _modulo_metadata()
    elif submodulo.startswith("1.2"):
        _modulo_scoring_unico(estado_jvm, usuario)
    else:
        _modulo_scoring_multiple(estado_jvm, usuario)
