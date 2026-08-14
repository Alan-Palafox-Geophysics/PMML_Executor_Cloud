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

    # --- [2] DICCIONARIO DE DATOS Y SALIDAS GLOBALES ---
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
        
    # --- [3] TRANSFORMACIONES GLOBALES (FEATURE ENGINEERING) ---
    print("--- [3] TRANSFORMACIONES GLOBALES (Feature Engineering) ---")
    transformaciones = []
    for derived in root.findall('.//pmml:TransformationDictionary/pmml:DerivedField', ns):
        field_ref = derived.find('pmml:FieldRef', ns)
        ref_name = field_ref.get('field') if field_ref is not None else 'Sin Referencia'
        transformaciones.append({
            'Variable Derivada': derived.get('name'),
            'Calculada a partir de': ref_name,
            'Tipo de Dato': derived.get('dataType', 'N/A')
        })
        
    if transformaciones:
        df_trans = pd.DataFrame(transformaciones)
        print(df_trans.to_string(index=False))
    else:
        print("  • No se detectaron transformaciones globales.")
    print("-" * 50 + "\n")

    # --- [4] ARQUITECTURA, FLUJOS Y SUBPROCESOS (RECURSIVO) ---
    print("--- [4] TRAZABILIDAD DE MODELOS Y SUBPROCESOS (Flujo de Datos) ---")
    
    def rastrear_modelo(nodo_modelo, nivel=1, nombre_segmento="Modelo Principal"):
        tipo_nodo = nodo_modelo.tag.split('}')[-1]
        algoritmo = nodo_modelo.get('algorithmName', tipo_nodo)
        funcion = nodo_modelo.get('functionName', 'No Definida')
        
        print(f"\n{'-'*15} Nivel {nivel} | Instancia: {nombre_segmento} | Algoritmo: {algoritmo} {'-'*15}")
        print(f" -> Función objetivo del nodo: {funcion}")
        
        # 1. ENTRADAS a este subproceso
        schema = nodo_modelo.find('pmml:MiningSchema', ns)
        if schema is not None:
            entradas = [f.get('name') for f in schema.findall('pmml:MiningField', ns)]
            print(f" [ENTRADAS] El nodo ingiere {len(entradas)} variables:")
            for e in entradas:
                print(f"    * {e}")
        else:
            print(" [ENTRADAS] Variables heredadas del nodo padre.")

        # 2. Transformaciones locales en este subproceso
        locales = nodo_modelo.find('pmml:LocalTransformations', ns)
        if locales is not None:
            trans_locales = locales.findall('pmml:DerivedField', ns)
            print(f" [PROCESO] Se aplican {len(trans_locales)} transformaciones matemáticas internas.")

        # 3. SALIDAS de este subproceso
        output = nodo_modelo.find('pmml:Output', ns)
        if output is not None:
            salidas = output.findall('pmml:OutputField', ns)
            print(f" [SALIDAS] El nodo genera {len(salidas)} variables hacia la siguiente capa:")
            for s in salidas:
                print(f"    * {s.get('name')} (Feature: {s.get('feature', 'N/A')}, Tipo: {s.get('dataType', 'N/A')})")
        else:
            print(" [SALIDAS] Output estándar del algoritmo (ej. valor en bruto / score final).")

        # 4. Recursividad (Ensamble / Bifurcación)
        segmentacion = nodo_modelo.find('pmml:Segmentation', ns)
        if segmentacion is not None:
            metodo = segmentacion.get('multipleModelMethod', 'Desconocido')
            segmentos_hijos = segmentacion.findall('pmml:Segment', ns)
            print(f"\n [BIFURCACIÓN] El nodo divide el cálculo en {len(segmentos_hijos)} sub-modelos. Método: {metodo}")
            
            # Prevenir spam visual si son Boosting Trees
            if metodo == 'sum' and len(segmentos_hijos) > 10:
                print(f"    -> [!] ATENCIÓN: Se detectaron {len(segmentos_hijos)} iteraciones sumativas (Boosted Trees).")
                print("    -> Se omite el desglose árbol por árbol para mantener legible la estructura de variables.")
            else:
                for idx, seg in enumerate(segmentos_hijos):
                    hijo = None
                    for etiqueta in ['pmml:MiningModel', 'pmml:RegressionModel', 'pmml:TreeModel']:
                        hijo = seg.find(etiqueta, ns)
                        if hijo is not None:
                            break
                    if hijo is not None:
                        rastrear_modelo(hijo, nivel + 1, f"Segmento ID {seg.get('id', str(idx+1))}")

    # Ejecutar la búsqueda jerárquica desde el nodo principal
    raiz_modelo = root.find('.//pmml:MiningModel', ns)
    if raiz_modelo is not None:
        rastrear_modelo(raiz_modelo)
    else:
        print("\n  No se encontró una estructura MiningModel en el archivo.")

    print("\n" + "=" * 70)
    print("                    FIN DEL ANÁLISIS COMPLETO                         ")
    print("=" * 70)

# Para usarlo:
# analizar_pmml_universal('stacking_Poco_Vinculados.pmml')