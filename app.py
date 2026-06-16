import os
import io
import sys
import json
import pandas as pd
import streamlit as st
import plotly.express as px
import plotly.graph_objects as go

# -----------------------------------------------------------------------------
# IMPORTACIÓN COHERENTE DE TUS MÓDULOS DE BACKEND
# -----------------------------------------------------------------------------
try:
    import PMML_Extract_Metadata as meta_extractor
    import PMML_Single_PyExecutor as single_executor
    import PMML_Multiple_PyExecutor as multiple_executor
except ImportError as e:
    st.error(f"❌ Error crítico de inicialización: No se pudo encontrar el módulo de backend '{e.name}'. "
             f"Asegúrate de que los archivos .py estén en el mismo directorio de esta app.")
    st.stop()

# -----------------------------------------------------------------------------
# CONFIGURACIÓN DE LA PÁGINA
# -----------------------------------------------------------------------------
st.set_page_config(
    page_title="PMML & Power Curve Risk Engine",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Inicializar variables globales en session state
if "authenticated" not in st.session_state:
    st.session_state.authenticated = False
if "merged_df" not in st.session_state:
    st.session_state.merged_df = None
if "pk_column" not in st.session_state:
    st.session_state.pk_column = None
if "multi_pmml_files" not in st.session_state:
    st.session_state.multi_pmml_files = {}

# -----------------------------------------------------------------------------
# PANTALLA DE CONTROL DE ACCESO (LOGIN)
# -----------------------------------------------------------------------------
def login_form():
    st.markdown("<h2 style='text-align: center;'>Control de Acceso Engine</h2>", unsafe_allow_html=True)
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        with st.form("login_form"):
            username = st.text_input("Usuario", placeholder="Ingrese su usuario")
            password = st.text_input("Contraseña", type="password", placeholder="••••••••")
            submit = st.form_submit_button("Ingresar al Sistema", use_container_width=True)
            
            if submit:
                if username == "rt_bistro" and password == "parametrias":
                    st.session_state.authenticated = True
                    st.success("Autenticación exitosa. Cargando entorno...")
                    st.rerun()
                else:
                    st.error("Credenciales incorrectas. Verifique usuario o contraseña.")

if not st.session_state.authenticated:
    login_form()
    st.stop()

# -----------------------------------------------------------------------------
# INTERFAZ PRINCIPAL - DISEÑO DE 4 PESTAÑAS
# -----------------------------------------------------------------------------
st.title("🛡️ PMML & Power Curve Analytics Workspace")
st.caption("Entorno unificado de validación, scoring masivo y conciliación de matrices de riesgo.")

tab1, tab2, tab3, tab4 = st.tabs([
    "🚀 Ejecución PMML", 
    "🔀 Consolidación y Validación (Merge)", 
    "📈 Gráficos de Comparación", 
    "⏳ Próximamente"
])

# -----------------------------------------------------------------------------
# PESTAÑA 1: EJECUCIÓN PMML (INTEGRACIÓN DE TUS MÓDULOS)
# -----------------------------------------------------------------------------
with tab1:
    st.header("Módulos de Ejecución e Inferencia Nativos")
    
    # --- SECCIÓN 1.1: PMML - METADATA ---
    with st.expander("📝 1.1 PMML - Metadata", expanded=True):
        st.subheader("Extracción de Metadatos y Firma del Modelo")
        meta_pmml = st.file_uploader("Subir archivo PMML para extracción", type=["pmml", "xml"], key="meta_pmml")
        
        is_meta_disabled = meta_pmml is None
        
        if st.button("Ejecutar Extracción", disabled=is_meta_disabled, key="btn_meta"):
            with st.spinner("Procesando estructura XML del archivo PMML..."):
                temp_pmml_path = f"temp_meta_{meta_pmml.name}"
                try:
                    with open(temp_pmml_path, "wb") as f:
                        f.write(meta_pmml.getbuffer())
                    
                    # Redirigir stdout para capturar los prints de analizar_pmml_universal
                    old_stdout = sys.stdout
                    sys.stdout = buffer = io.StringIO()
                    
                    meta_extractor.analizar_pmml_universal(temp_pmml_path)
                    
                    sys.stdout = old_stdout
                    log_content = buffer.getvalue()
                    
                    st.success("✅ Análisis completado con éxito.")
                    st.text_area("Vista previa del log de auditoría:", value=log_content, height=250)
                    
                    st.download_button(
                        label="📥 Descargar Log de Auditoría (.txt)",
                        data=log_content,
                        file_name=f"log_metadata_{meta_pmml.name}.txt",
                        mime="text/plain",
                        use_container_width=True
                    )
                    
                except Exception as e:
                    st.error(f"Fallo al ejecutar la extracción de metadatos: {str(e)}")
                finally:
                    if os.path.exists(temp_pmml_path):
                        os.remove(temp_pmml_path)

    # --- SECCIÓN 1.2: EVALUACIÓN DE PMML ÚNICO ---
    with st.expander("🎯 1.2 Evaluación de PMML Único", expanded=False):
        st.subheader("Scoring Unificado (Single Model)")
        single_pmml = st.file_uploader("Subir archivo .pmml del modelo", type=["pmml"], key="single_pmml")
        single_data = st.file_uploader("Subir conjunto de datos a evaluar (.csv)", type=["csv"], key="single_data")
        
        is_single_disabled = not (single_pmml and single_data)
        
        if st.button("Ejecutar Scoring Único", disabled=is_single_disabled):
            with st.spinner("Inicializando JVM y calculando probabilidades del modelo único..."):
                t_pmml = f"temp_single_{single_pmml.name}"
                t_data = f"temp_data_{single_data.name}"
                try:
                    with open(t_pmml, "wb") as f: f.write(single_pmml.getbuffer())
                    with open(t_data, "wb") as f: f.write(single_data.getbuffer())
                    
                    df_scored = single_executor.PMML_Single_Executor(data_path=t_data, pmml_path=t_pmml)
                    
                    st.success("✅ Motor de evaluación finalizado con éxito.")
                    st.dataframe(df_scored.head(10), use_container_width=True)
                    
                    csv_scored_single = df_scored.to_csv(index=False).encode('utf-8')
                    st.download_button(
                        label="📥 Descargar Resultado del Scoring Único (CSV)",
                        data=csv_scored_single,
                        file_name="resultado_scoring_unico.csv",
                        mime="text/csv",
                        use_container_width=True
                    )
                except Exception as e:
                    st.error(f"Error crítico en la ejecución del PMML Único: {str(e)}")
                finally:
                    if os.path.exists(t_pmml): os.remove(t_pmml)
                    if os.path.exists(t_data): os.remove(t_data)

    # --- SECCIÓN 1.3: EVALUACIÓN DE PMML MÚLTIPLE (CARGA DINÁMICA) ---
    with st.expander("🗂️ 1.3 Evaluación de PMML Múltiple", expanded=False):
        st.subheader("Scoring Segmentado y Enrutamiento Multimodelo")
        
        multi_json = st.file_uploader("1. Subir archivo de distribución de segmentos (.json)", type=["json"], key="multi_json")
        
        # Diccionario intermedio para mapear la carga secuencial de PMMLs
        pmml_upload_pointers = {}
        json_config_dict = None
        
        if multi_json:
            try:
                # Leer la estructura del archivo JSON en memoria de forma segura
                json_config_dict = json.load(multi_json)
                pmml_mapping = json_config_dict.get("pmml_files", {})
                
                if not pmml_mapping:
                    st.error("El archivo JSON no tiene una estructura válida con la llave 'pmml_files'.")
                else:
                    st.markdown("##### 📦 Carga Secuencial de Modelos PMML Requeridos:")
                    # Iterar respetando el orden secuencial definido por el JSON
                    for segment, pmml_filename in pmml_mapping.items():
                        pmml_upload_pointers[segment] = st.file_uploader(
                            f"Segmento: **{segment}** ➡️ Subir archivo: `{pmml_filename}`", 
                            type=["pmml"], 
                            key=f"upload_multi_{segment}"
                        )
            except Exception as e:
                st.error(f"Error al parsear el archivo de configuración JSON: {e}")

        st.markdown("---")
        multi_data = st.file_uploader("2. Subir dataset matriz a evaluar (.csv)", type=["csv"], key="multi_data")
        segment_var = st.text_input("3. Nombre exacto de la variable de enrutamiento (Segmento)", placeholder="Ej: segmento_id")
        
        # Validar si todos los archivos de los segmentos del JSON han sido subidos correctamente
        all_pmmls_uploaded = False
        if json_config_dict and pmml_upload_pointers:
            all_pmmls_uploaded = all(file is not None for file in pmml_upload_pointers.values())
            
        is_multi_disabled = not (multi_json and all_pmmls_uploaded and multi_data and segment_var.strip() != "")
        
        if st.button("Ejecutar Scoring Múltiple", disabled=is_multi_disabled):
            with st.spinner("Segmentando vectores de datos y enrutando a evaluadores JPMML paralelos..."):
                t_json = f"temp_multi_config.json"
                t_data_m = f"temp_datam_{multi_data.name}"
                created_temp_files = []
                
                try:
                    # Crear en la raíz un directorio temporal ficticio para el backend compatible con el JSON
                    os.makedirs("temp_pmmls", exist_ok=True)
                    json_config_dict["general_path"] = "temp_pmmls"
                    
                    # Escribir los bytes de cada PMML subido dinámicamente usando el nombre exigido en la firma del JSON
                    for segment, file_obj in pmml_upload_pointers.items():
                        target_filename = json_config_dict["pmml_files"][segment]
                        temp_pmml_route = os.path.join("temp_pmmls", target_filename)
                        with open(temp_pmml_route, "wb") as f:
                            f.write(file_obj.getbuffer())
                        created_temp_files.append(temp_pmml_route)
                    
                    # Guardar archivo JSON de configuración adaptado
                    with open(t_json, "w", encoding="utf-8") as f:
                        json.dump(json_config_dict, f, ensure_ascii=False, indent=4)
                        
                    with open(t_data_m, "wb") as f: 
                        f.write(multi_data.getbuffer())
                    
                    df_scored_multi = multiple_executor.PMML_PyExecutor(
                        data_path=t_data_m, 
                        segment_variable=segment_var, 
                        config_path=t_json
                    )
                    
                    st.success("✅ Ejecución Multimodelo completada.")
                    st.dataframe(df_scored_multi.head(10), use_container_width=True)
                    
                    csv_scored_multi = df_scored_multi.to_csv(index=False).encode('utf-8')
                    st.download_button(
                        label="📥 Descargar Resultados Multiplexados (CSV)",
                        data=csv_scored_multi,
                        file_name="resultado_scoring_multiple.csv",
                        mime="text/csv",
                        use_container_width=True
                    )
                except Exception as e:
                    st.error(f"Error crítico en la ejecución del PMML Múltiple: {str(e)}")
                finally:
                    # Garantizar la eliminación total de rastros del sistema de archivos en la nube
                    if os.path.exists(t_json): os.remove(t_json)
                    if os.path.exists(t_data_m): os.remove(t_data_m)
                    for t_file in created_temp_files:
                        if os.path.exists(t_file): os.remove(t_file)
                    if os.path.exists("temp_pmmls"):
                        try: os.rmdir("temp_pmmls")
                        except: pass

# -----------------------------------------------------------------------------
# PESTAÑA 2: CONSOLIDACIÓN Y VALIDACIÓN (MERGE POWER CURVE)
# -----------------------------------------------------------------------------
with tab2:
    st.header("Módulo de Conciliación y Cruce de Matrices")
    
    st.markdown("### Paso 1: Carga de Datos")
    col_a, col_b, col_c = st.columns(3)
    with col_a:
        file_pmml_res = st.file_uploader("Resultados PMML (Obligatorio)", type=["csv", "parquet"], key="f_pmml")
    with col_b:
        file_pwc = st.file_uploader("Datos Power Curve (Obligatorio)", type=["csv", "parquet"], key="f_pwc")
    with col_c:
        file_cifras = st.file_uploader("Archivo de Cifras Control (Opcional)", type=["csv", "parquet"], key="f_cifras")
        
    if file_pmml_res and file_pwc:
        st.markdown("---")
        st.markdown("### Paso 2: Configuración del Merge")
        
        try:
            df_pmml = pd.read_csv(file_pmml_res) if file_pmml_res.name.endswith('.csv') else pd.read_parquet(file_pmml_res)
            df_pwc_raw = pd.read_csv(file_pwc) if file_pwc.name.endswith('.csv') else pd.read_parquet(file_pwc)
        except Exception as e:
            st.error(f"Error al leer los archivos base cargados: {e}")
            st.stop()
            
        col_cfg1, col_cfg2 = st.columns(2)
        with col_cfg1:
            pk_col = st.selectbox("Seleccione la Variable de Comparación (Primary Key)", options=df_pmml.columns.tolist())
        with col_cfg2:
            prefix_to_remove = st.text_input("Prefijo a eliminar en variables del dataset Power Curve", placeholder="Ej: PWC_")
            
        st.markdown("### Paso 3: Lógica de Unión")
        if st.button("Ejecutar Merge / Conciliación", use_container_width=True):
            with st.spinner("Procesando cruce de información y renombrado dinámico de variables..."):
                try:
                    df_pwc = df_pwc_raw.copy()
                    
                    if prefix_to_remove.strip():
                        df_pwc.columns = [
                            col.replace(prefix_to_remove, "") if col.startswith(prefix_to_remove) else col 
                            for col in df_pwc.columns
                        ]
                        
                    if pk_col not in df_pwc.columns:
                        st.error(f"Error: La llave '{pk_col}' no existe en Power Curve tras eliminar el prefijo.")
                        st.stop()
                    
                    pwc_keep_cols = [
                        col for col in df_pwc.columns 
                        if "probability" in col.lower() or "target" in col.lower() or "segment" in col.lower() or col == pk_col
                    ]
                    df_pwc_filtered = df_pwc[pwc_keep_cols].copy()
                    
                    df_pwc_filtered.columns = [
                        f"pwc_{col}" if col != pk_col else col for col in df_pwc_filtered.columns
                    ]
                    
                    df_pmml[pk_col] = df_pmml[pk_col].astype(str).str.strip()
                    df_pwc_filtered[pk_col] = df_pwc_filtered[pk_col].astype(str).str.strip()
                    
                    df_final = pd.merge(df_pmml, df_pwc_filtered, on=pk_col, how="inner")
                    
                    if file_cifras:
                        df_cifras = pd.read_csv(file_cifras) if file_cifras.name.endswith('.csv') else pd.read_parquet(file_cifras)
                        cifras_keep_cols = [
                            col for col in df_cifras.columns 
                            if "probability" in col.lower() or "target" in col.lower() or "segment" in col.lower() or col == pk_col
                        ]
                        df_cifras_filtered = df_cifras[cifras_keep_cols].copy()
                        df_cifras_filtered.columns = [
                            f"CifrasControl_{col}" if col != pk_col else col for col in df_cifras_filtered.columns
                        ]
                        df_cifras_filtered[pk_col] = df_cifras_filtered[pk_col].astype(str).str.strip()
                        df_final = pd.merge(df_final, df_cifras_filtered, on=pk_col, how="inner")
                    
                    st.session_state.merged_df = df_final
                    st.session_state.pk_column = pk_col
                    st.success(f"Merge finalizado con éxito. Dimensiones del set consolidado: {df_final.shape[0]} registros.")
                except Exception as e:
                    st.error(f"Fallo en la matriz lógica de unión: {str(e)}")
                    
        if st.session_state.merged_df is not None:
            st.markdown("---")
            st.markdown("### Paso 4: Visualización y Exportación")
            
            st.dataframe(st.session_state.merged_df, use_container_width=True)
            
            csv_data = st.session_state.merged_df.to_csv(index=False).encode('utf-8')
            st.download_button(
                label="📥 Descargar Matriz Consolidada resultante (CSV)",
                data=csv_data,
                file_name="matriz_consolidada_scoring.csv",
                mime="text/csv",
                use_container_width=True
            )
    else:
        st.info("Por favor, cargue los dos datasets obligatorios iniciales para desplegar los paneles de configuración.")

# -----------------------------------------------------------------------------
# PESTAÑA 3: GRÁFICOS DE COMPARACIÓN (ANÁLISIS DE RESIDUOS)
# -----------------------------------------------------------------------------
with tab3:
    st.header("Análisis Estadístico de Desviaciones y Residuos")
    
    if st.session_state.merged_df is None:
        st.warning("⚠️ No se ha detectado ninguna matriz de datos unificada en la sesión. Procesa el cruce en la Pestaña 2.")
    else:
        df_analysis = st.session_state.merged_df.copy()
        
        st.markdown("### 📊 Análisis de Residuos: Python (PMML) vs Power Curve")
        
        prob_cols_py = [col for col in df_analysis.columns if "probability" in col.lower() and not col.startswith(('pwc_', 'CifrasControl_'))]
        prob_cols_pwc = [col for col in df_analysis.columns if col.startswith('pwc_') and "probability" in col.lower()]
        
        if prob_cols_py and prob_cols_pwc:
            col_sel_py = st.selectbox("Seleccione columna de probabilidad Python", options=prob_cols_py)
            col_sel_pwc = st.selectbox("Seleccione columna de probabilidad Power Curve (PwC)", options=prob_cols_pwc)
            
            # Menú desplegable para columna de segmentación solicitado debajo de los de probabilidad
            col_segmentacion = st.selectbox(
                "Seleccione columna de segmentación (Opcional, dejar en 'Ninguna' por default)", 
                options=["Ninguna"] + df_analysis.columns.tolist()
            )
            
            df_analysis[col_sel_py] = pd.to_numeric(df_analysis[col_sel_py], errors='coerce')
            df_analysis[col_sel_pwc] = pd.to_numeric(df_analysis[col_sel_pwc], errors='coerce')
            
            # Cálculo del error porcentual solicitado: (Python - PwC) / Python * 100
            # Se añade un pequeño epsilon para evitar división por cero en registros de probabilidad nula
            df_analysis['error_porcentual'] = ((df_analysis[col_sel_py] - df_analysis[col_sel_pwc]) / (df_analysis[col_sel_py] + 1e-9)) * 100
            
            # Evaluar si se especificó una segmentación válida para asignar colores
            color_param = None if col_segmentacion == "Ninguna" else col_segmentacion
            
            g_col1, g_col2 = st.columns(2)
            with g_col1:
                st.subheader("Distribución de Residuos (Errores)")
                # Gráfico modificado para reflejar análisis de residuo en error porcentual (Y) vs Variable (X)
                fig_hist = px.scatter(
                    df_analysis, 
                    x=col_sel_py, 
                    y="error_porcentual", 
                    color=color_param,
                    title="Análisis de Desviaciones: Error Porcentual vs Probabilidad",
                    labels={col_sel_py: 'Valor de la Variable (Probabilidad Python)', 'error_porcentual': 'Error Porcentual (%)'},
                    color_discrete_sequence=['#FF4B4B'] if color_param is None else None,
                    opacity=0.6
                )
                # Línea horizontal en cero para observar la desviación de los datos
                fig_hist.add_hline(y=0, line_dash="dash", line_color="black", annotation_text="Línea de cero error")
                st.plotly_chart(fig_hist, use_container_width=True)
                
            with g_col2:
                st.subheader("Gráfico de Dispersión e Identidad")
                fig_scatter = px.scatter(
                    df_analysis, x=col_sel_py, y=col_sel_pwc,
                    color=color_param,
                    title="Correlación Exacta de Probabilidades de Riesgo",
                    labels={col_sel_py: 'Eje Python + PMML', col_sel_pwc: 'Eje Power Curve'},
                    opacity=0.6
                )
                min_val = min(df_analysis[col_sel_py].min(), df_analysis[col_sel_pwc].min())
                max_val = max(df_analysis[col_sel_py].max(), df_analysis[col_sel_pwc].max())
                fig_scatter.add_trace(go.Scatter(
                    x=[min_val, max_val], y=[min_val, max_val], 
                    mode='lines', name='Línea Ideal de 45°', 
                    line=dict(dash='dash', color='gray'),
                    showlegend=True if color_param is None else False
                ))
                st.plotly_chart(fig_scatter, use_container_width=True)
                
            prob_cols_cc = [col for col in df_analysis.columns if col.startswith('CifrasControl_') and "probability" in col.lower()]
            if prob_cols_cc:
                st.markdown("---")
                st.markdown("### 📉 Análisis de Residuos: Cifras Control vs Power Curve")
                col_sel_cc = st.selectbox("Seleccione columna de probabilidad de Cifras Control", options=prob_cols_cc)
                
                df_analysis[col_sel_cc] = pd.to_numeric(df_analysis[col_sel_cc], errors='coerce')
                df_analysis['residuo_cc'] = df_analysis[col_sel_cc] - df_analysis[col_sel_pwc]
                
                cc_col1, cc_col2 = st.columns(2)
                with cc_col1:
                    fig_hist_cc = px.histogram(
                        df_analysis, x="residuo_cc", nbins=50, 
                        title="Frecuencia de Desviaciones (Cifras Control - PwC)",
                        labels={'residuo_cc': 'Magnitud del Residuo'},
                        color_discrete_sequence=['#00CC96']
                    )
                    st.plotly_chart(fig_hist_cc, use_container_width=True)
                with cc_col2:
                    fig_scatter_cc = px.scatter(
                        df_analysis, x=col_sel_cc, y=col_sel_pwc,
                        title="Correlación Cifras Control vs Power Curve",
                        labels={col_sel_cc: 'Cifras Control', col_sel_pwc: 'Power Curve'},
                        opacity=0.6
                    )
                    st.plotly_chart(fig_scatter_cc, use_container_width=True)
        else:
            st.error("No se encontraron variables con la convención de nombre 'probability' en los sets combinados.")

# -----------------------------------------------------------------------------
# PESTAÑA 4: PROXIMAMENTE
# -----------------------------------------------------------------------------
with tab4:
    st.info("⏳ Sección reservada para futuros módulos analíticos de validación del área de Riesgos (Backtesting de Modelos, Curvas ROC/Gini o Estabilidad de Población PSI).")