import xml.etree.ElementTree as ET
import pandas as pd

def analizar_pmml_universal(ruta_archivo):
    namespaces = {
        'pmml': 'http://www.dmg.org/PMML-4_4',
        'pmml_alt': 'http://www.dmg.org/PMML-4_3'
    }
    
    print("=" * 70)
    print("      AUDITOR Y PARSER UNIVERSAL DE MODELOS PMML (ML & RISK)   ")
    print("=" * 70 + "\n")
    
    try:
        tree = ET.parse(ruta_archivo)
        root = tree.getroot()
    except Exception as e:
        print(f"Error al leer el archivo XML: {e}")
        return

    ns_uri = root.tag.split('}')[0].strip('{') if '}' in root.tag else 'http://www.dmg.org/PMML-4_4'
    ns = {'pmml': ns_uri}

    header = root.find('pmml:Header', ns)
    if header is not None:
        app = header.find('pmml:Application', ns)
        timestamp = header.find('pmml:Timestamp', ns)
        print("--- [1] METADATA DEL ENCABEZADO ---")
        print(f"  • Aplicación / Librería: {app.get('name') if app is not None else 'No especificado'}")
        print(f"  • Versión del Exportador: {app.get('version') if app is not None else 'No especificada'}")
        print(f"  • Fecha de Creación: {timestamp.text if timestamp is not None else 'No registrada'}\n")

    # --- [2] MODIFICADO: PRIORIDAD A OUTPUTFIELDS Y DESPLIEGUE EN TABLAS COMPLETAS ---
    data_dict = root.find('pmml:DataDictionary', ns)
    variables_entrada = []
    variables_salida = []
    target_var = "No detectado"
    
    # 1. Extraer con prioridad las variables reales de salida de los bloques OutputField
    for out_field in root.findall('.//pmml:OutputField', ns):
        out_name = out_field.get('name')
        out_datatype = out_field.get('dataType', 'No especificado')
        out_feature = out_field.get('feature', 'Output')
        
        variables_salida.append({
            'Variable de Salida': out_name,
            'Tipo': f"Predicción ({out_feature})",
            'Tipo de Dato': out_datatype
        })

    # 2. Procesar el DataDictionary para inputs y auditoría de la variable Target original
    if data_dict is not None:
        for field in data_dict.findall('pmml:DataField', ns):
            name = field.get('name')
            optype = field.get('optype')
            datatype = field.get('dataType')
            
            if name.lower() in ['target', 'objetivo', 'clase', 'status']:
                target_var = f"{name} [Tipo: {optype} | Dato: {datatype}]"
                # Añadir el target a la tabla de salidas solo si no fue capturado en los OutputFields
                if not any(d['Variable de Salida'] == name for d in variables_salida):
                    variables_salida.append({
                        'Variable de Salida': name,
                        'Tipo': 'Target (Adicional)',
                        'Tipo de Dato': datatype
                    })
            else:
                variables_entrada.append({
                    'Variable de Entrada': name, 
                    'Tipo Operativo': optype, 
                    'Tipo de Dato': datatype
                })

    print("--- [2] CAMPOS DEL DICCIONARIO DE DATOS Y SALIDAS ---")
    print(f"  • Variable de Salida Base (Target): {target_var}")
    print(f"  • Total de Variables de Entrada (Predictoras): {len(variables_entrada)}")
    print(f"  • Total de Variables de Salida Detectadas: {len(variables_salida)}")
    
    if variables_entrada:
        df_vars = pd.DataFrame(variables_entrada)
        print("\n--- TABLA DE VARIABLES DE ENTRADA (TODAS) ---")
        print(df_vars.to_string(index=False))
        print("-" * 50)

    if variables_salida:
        df_outputs = pd.DataFrame(variables_salida)
        print("\n--- TABLA DE VARIABLES DE SALIDA (PRIORITARIAS) ---")
        print(df_outputs.to_string(index=False))
        print("-" * 50 + "\n")
    # ---------------------------------------------------------------------------------

    print("--- [3] ARQUITECTURA Y FLUJO JERÁRQUICO DE MODELOS ---")
    
    mining_models = root.findall('.//pmml:MiningModel', ns)
    regression_models = root.findall('.//pmml:RegressionModel', ns)
    tree_models = root.findall('.//pmml:TreeModel', ns)
    
    if len(mining_models) > 0:
        print(f"  [Estructura Detectada]: Ensamble Complejo / Pipeline de Múltiples Capas.")
        for idx, m_model in enumerate(mining_models, 1):
            alg_name = m_model.get('algorithmName', 'No definido')
            func_name = m_model.get('functionName', 'No definida')
            print(f"    -> Capa Lógica {idx}: {alg_name} (Función Objetivo: {func_name})")
            
            segmentation = m_model.find('.//pmml:Segmentation', ns)
            if segmentation is not None:
                method = segmentation.get('multipleModelMethod', 'Desconocido')
                print(f"       • Método de Enlace de la Capa: '{method}'")
    else:
        print("  [Estructura Detectada]: Pipeline Lineal Estándar de una sola capa.")

    print("\n--- [4] AUDITORÍA DE ALGORITMOS E ITERACIONES ---")
    
    if len(tree_models) > 0:
        print(f"  • Algoritmos de Árboles (XGBoost / Árboles de Decisión / RF): DETECTADO")
        print(f"    -> Número total de iteraciones estimadas (Árboles individuales / Boosts): {len(tree_models)}")
        func_arboles = set([t.get('functionName') for t in tree_models])
        print(f"    -> Naturaleza funcional de los árboles internos: {list(func_arboles)}")
    else:
        print("  • Algoritmos de Árboles: No se encontraron sub-estructuras TreeModel.")

    if len(regression_models) > 0:
        print(f"  • Modelos Basados en Regresión (Logística / Lineal / Scorecards WoE): DETECTADO")
        print(f"    -> Cantidad total de bloques de regresión activos: {len(regression_models)}")
        for idx, r_model in enumerate(regression_models, 1):
            r_alg = r_model.get('algorithmName', 'Regresión Estándar')
            r_func = r_model.get('functionName', 'No definida')
            print(f"    -> Bloque {idx}: '{r_alg}' optimizado para '{r_func}'")
            
            intercept = r_model.find('.//pmml:RegressionTable', ns)
            if intercept is not None and intercept.get('intercept') is not None:
                print(f"       • Intercepto base calculado (Bias): {intercept.get('intercept')}")
    else:
        print("  • Modelos Basados en Regresión: No se encontraron bloques de coeficientes lineales.")

    print("\n" + "=" * 70)
    print("                    FIN DEL ANÁLISIS COMPLETO                         ")
    print("=" * 70)