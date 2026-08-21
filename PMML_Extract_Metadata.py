import xml.etree.ElementTree as ET
import pandas as pd
import io

def analizar_pmml_estructurado(ruta_archivo):
    """
    Parsea el PMML y retorna un diccionario estructurado ideal para Dashboards en Streamlit,
    además del log tradicional en texto plano para auditoría.
    """
    namespaces = {
        'pmml': 'http://www.dmg.org/PMML-4_4',
        'pmml_alt': 'http://www.dmg.org/PMML-4_3'
    }
    
    dict_output = {
        "header": {},
        "inputs": [],
        "outputs": [],
        "transformations": [],
        "flow": [],
        "raw_log": ""
    }
    
    # Capturador de log tradicional
    log_buffer = io.StringIO()
    def log_print(msg):
        log_buffer.write(msg + "\n")
        
    log_print("=" * 70)
    log_print("      AUDITOR Y PARSER UNIVERSAL DE MODELOS PMML (ML & RISK)   ")
    log_print("=" * 70 + "\n")
    
    try:
        tree = ET.parse(ruta_archivo)
        root = tree.getroot()
    except Exception as e:
        log_print(f"Error al leer el archivo XML: {e}")
        dict_output["raw_log"] = log_buffer.getvalue()
        return dict_output

    ns_uri = root.tag.split('}')[0].strip('{') if '}' in root.tag else 'http://www.dmg.org/PMML-4_4'
    ns = {'pmml': ns_uri}

    # [1] METADATA DEL ENCABEZADO
    header = root.find('pmml:Header', ns)
    if header is not None:
        app = header.find('pmml:Application', ns)
        timestamp = header.find('pmml:Timestamp', ns)
        
        app_name = app.get('name') if app is not None else 'No especificado'
        app_version = app.get('version') if app is not None else 'No especificada'
        creation_date = timestamp.text if timestamp is not None else 'No registrada'
        
        dict_output["header"] = {
            "Aplicacion": app_name,
            "Version": app_version,
            "Fecha": creation_date
        }
        
        log_print("--- [1] METADATA DEL ENCABEZADO ---")
        log_print(f"  • Aplicación / Librería: {app_name}")
        log_print(f"  • Versión del Exportador: {app_version}")
        log_print(f"  • Fecha de Creación: {creation_date}\n")

    # [2] DICCIONARIO DE DATOS Y SALIDAS GLOBALES
    data_dict = root.find('pmml:DataDictionary', ns)
    target_var_str = "No detectado"
    
    for out_field in root.findall('.//pmml:OutputField', ns):
        out_name = out_field.get('name')
        out_datatype = out_field.get('dataType', 'No especificado')
        out_feature = out_field.get('feature', 'Output')
        
        dict_output["outputs"].append({
            'Variable de Salida': out_name,
            'Tipo': f"Predicción ({out_feature})",
            'Tipo de Dato': out_datatype
        })

    if data_dict is not None:
        for field in data_dict.findall('pmml:DataField', ns):
            name = field.get('name')
            optype = field.get('optype')
            datatype = field.get('dataType')
            
            if name.lower() in ['target', 'objetivo', 'clase', 'status']:
                target_var_str = f"{name} [Tipo: {optype} | Dato: {datatype}]"
                if not any(d['Variable de Salida'] == name for d in dict_output["outputs"]):
                    dict_output["outputs"].append({
                        'Variable de Salida': name,
                        'Tipo': 'Target (Adicional)',
                        'Tipo de Dato': datatype
                    })
            else:
                dict_output["inputs"].append({
                    'Variable de Entrada': name, 
                    'Tipo Operativo': optype, 
                    'Tipo de Dato': datatype
                })

    dict_output["header"]["Target"] = target_var_str
    log_print(f"--- [2] CAMPOS DEL DICCIONARIO DE DATOS ---\nTarget: {target_var_str}")

    # [3] TRANSFORMACIONES GLOBALES
    for derived in root.findall('.//pmml:TransformationDictionary/pmml:DerivedField', ns):
        field_ref = derived.find('pmml:FieldRef', ns)
        ref_name = field_ref.get('field') if field_ref is not None else 'Sin Referencia'
        dict_output["transformations"].append({
            'Variable Derivada': derived.get('name'),
            'Calculada a partir de': ref_name,
            'Tipo de Dato': derived.get('dataType', 'N/A')
        })

    # [4] ARQUITECTURA, FLUJOS Y SUBPROCESOS
    def rastrear_modelo(nodo_modelo, nivel=1, nombre_segmento="Modelo Principal"):
        tipo_nodo = nodo_modelo.tag.split('}')[-1]
        algoritmo = nodo_modelo.get('algorithmName', tipo_nodo)
        
        # Guardar en flujo estructurado
        dict_output["flow"].append({
            "nivel": nivel, 
            "instancia": nombre_segmento, 
            "algoritmo": algoritmo
        })
        
        log_print(f"-> Nivel {nivel} | Instancia: {nombre_segmento} | Algoritmo: {algoritmo}")
        
        segmentacion = nodo_modelo.find('pmml:Segmentation', ns)
        if segmentacion is not None:
            metodo = segmentacion.get('multipleModelMethod', 'Desconocido')
            segmentos_hijos = segmentacion.findall('pmml:Segment', ns)
            if metodo == 'sum' and len(segmentos_hijos) > 10:
                dict_output["flow"].append({
                    "nivel": nivel+1, 
                    "instancia": f"Ensamble ({len(segmentos_hijos)} árboles sumativos)", 
                    "algoritmo": "Gradient Boosting"
                })
            else:
                for idx, seg in enumerate(segmentos_hijos):
                    for etiqueta in ['pmml:MiningModel', 'pmml:RegressionModel', 'pmml:TreeModel']:
                        hijo = seg.find(etiqueta, ns)
                        if hijo is not None:
                            rastrear_modelo(hijo, nivel + 1, f"Segmento ID {seg.get('id', str(idx+1))}")
                            break

    raiz_modelo = root.find('.//pmml:MiningModel', ns)
    if raiz_modelo is not None:
        rastrear_modelo(raiz_modelo)
        
    dict_output["raw_log"] = log_buffer.getvalue()
    return dict_output

# Se mantiene la función original por compatibilidad por si otros módulos la llaman
def analizar_pmml_universal(ruta_archivo):
    data = analizar_pmml_estructurado(ruta_archivo)
    print(data["raw_log"])