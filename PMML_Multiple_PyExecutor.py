import os
import json
import logging
from typing import Dict, Any, Optional, List, Tuple
import pandas as pd
from jpmml_evaluator import make_evaluator

# OMITIR RUTAS LOCALES DE JAVA - Streamlit Cloud resuelve la JVM nativamente con packages.txt
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("PMML_Scoring_Engine")


def data_reader(
    data_path: str, types_path: Optional[str] = None, config_path: Optional[str] = None
) -> Tuple[pd.DataFrame, Optional[pd.DataFrame], Dict[str, Any]]:
    logger.info("Iniciando la carga de archivos base...")
    
    if not os.path.exists(data_path):
        raise FileNotFoundError(f"No se encontró el dataset principal en: {data_path}")
    df_data = pd.read_csv(data_path, dtype=str)
    logger.info(f"Dataset principal cargado exitosamente. Dimensiones: {df_data.shape}")

    df_types = None
    if types_path:
        if not os.path.exists(types_path):
            raise FileNotFoundError(f"No se encontró el archivo de tipos en: {types_path}")
        df_types = pd.read_csv(types_path)
        logger.info("Diccionario de tipos cargado exitosamente.")

    config = {}
    if config_path:
        if not os.path.exists(config_path):
            raise FileNotFoundError(f"No se encontró la configuración JSON en: {config_path}")
        with open(config_path, "r", encoding="utf-8") as f:
            config = json.load(f)
        logger.info("Configuración JSON cargada y parseada exitosamente.")

    return df_data, df_types, config


def data_transformer(df: pd.DataFrame, schema_mapping: Dict[str, str]) -> pd.DataFrame:
    df_casted = df.copy()
    for column, data_type in schema_mapping.items():
        if column in df_casted.columns:
            try:
                df_casted[column] = df_casted[column].astype(data_type)
            except Exception as e:
                logger.error(f"Error al castear la columna '{column}' al tipo '{data_type}': {str(e)}")
                raise e
    return df_casted


class PMMLManager:
    def __init__(self, config: Dict[str, Any]):
        self.general_path = config.get("general_path", "")
        self.models_mapping = config.get("pmml_files", {})
        self.loaded_models: Dict[str, Any] = {}
        
        self._type_fallback_map = {
            "double": "float64",
            "float": "float32",
            "integer": "int64",
            "int": "int64",
            "string": "object",
            "boolean": "bool"
        }
        self._preload_models()

    def _preload_models(self) -> None:
        logger.info("Pre-cargando modelos PMML en memoria mediante jpmml_evaluator...")
        if not self.models_mapping:
            raise ValueError("La configuración JSON no contiene un mapeo de modelos válido bajo la llave 'pmml_files'.")
            
        for segment, pmml_file in self.models_mapping.items():
            full_path = os.path.join(self.general_path, pmml_file)
            if not os.path.exists(full_path):
                raise FileNotFoundError(f"Archivo PMML no encontrado para segmento '{segment}': {full_path}")
            
            evaluator = make_evaluator(full_path)
            self.loaded_models[segment] = evaluator
            logger.info(f"Modelo JPMML para segmento '{segment}' cargado exitosamente.")

    @property
    def is_single_model(self) -> bool:
        return len(self.loaded_models) == 1

    @property
    def single_segment_name(self) -> str:
        return list(self.loaded_models.keys())[0]

    def get_pmml_schema(self, segment: str) -> Dict[str, str]:
        model = self.loaded_models.get(segment)
        if not model:
            raise ValueError(f"No existe un modelo cargado para el segmento: {segment}")
            
        schema = {}
        for field in model.getInputFields():
            field_name = str(field.getName()) if hasattr(field, 'getName') else str(field.name)
            
            if hasattr(field, 'getDataType') and field.getDataType() is not None:
                pmml_type = str(field.getDataType()).lower()
            else:
                pmml_type = str(getattr(field, 'dataType', 'string')).lower()
            
            if "double" in pmml_type: pmml_type = "double"
            elif "float" in pmml_type: pmml_type = "float"
            elif "integer" in pmml_type: pmml_type = "integer"
            elif "int" in pmml_type: pmml_type = "int"
            elif "boolean" in pmml_type: pmml_type = "boolean"
            elif "string" in pmml_type: pmml_type = "string"
            
            pandas_type = self._type_fallback_map.get(pmml_type, "object")
            schema[field_name] = pandas_type
            
        return schema

    def get_input_order(self, segment: str) -> List[str]:
        model = self.loaded_models[segment]
        return [str(field.getName()) if hasattr(field, 'getName') else str(field.name) for field in model.getInputFields()]

    def score_segment(self, df_segment: pd.DataFrame, segment: str) -> pd.DataFrame:
        if segment not in self.loaded_models:
            raise KeyError(f"Ejecución denegada: El segmento '{segment}' no tiene un modelo configurado.")

        model = self.loaded_models[segment]
        input_order = self.get_input_order(segment)
        
        missing_cols = [col for col in input_order if col not in df_segment.columns]
        if missing_cols:
            raise ValueError(f"El dataset carece de variables requeridas por el PMML '{segment}': {missing_cols}")

        df_scoring_input = df_segment[input_order]
        logger.info(f"Ejecutando scoring JPMML para el segmento '{segment}' con {len(df_segment)} registros.")
        
        df_predictions = model.evaluateAll(df_scoring_input)

        if isinstance(df_predictions, pd.Series):
            df_predictions = pd.DataFrame(df_predictions, columns=["prediction"])

        df_predictions.index = df_segment.index
        df_scored_output = pd.concat([df_segment, df_predictions], axis=1)
        
        return df_scored_output


def PMML_PyExecutor(
    data_path: str, segment_variable: Optional[str] = None, types_path: Optional[str] = None, config_path: Optional[str] = None
) -> pd.DataFrame:
    df_raw, df_types, config = data_reader(data_path, types_path, config_path)
    pmml_manager = PMMLManager(config)
    
    csv_schema_mapping = {}
    if df_types is not None:
        csv_schema_mapping = dict(zip(df_types.iloc[:, 0], df_types.iloc[:, 1]))

    processed_segments_chunks: List[pd.DataFrame] = []

    if pmml_manager.is_single_model:
        segment = pmml_manager.single_segment_name
        try:
            if df_types is not None:
                df_transformed = data_transformer(df_raw, csv_schema_mapping)
            else:
                pmml_native_schema = pmml_manager.get_pmml_schema(segment)
                df_transformed = data_transformer(df_raw, pmml_native_schema)

            df_scored = pmml_manager.score_segment(df_transformed, segment)
            df_scored["executed_segment"] = segment
            processed_segments_chunks.append(df_scored)
        except Exception as e:
            logger.error(f"Fallo crítico con modelo único '{segment}': {str(e)}")
            raise e
    else:
        if not segment_variable:
            raise ValueError("Se detectaron múltiples modelos, 'segment_variable' es mandatorio.")
            
        if segment_variable not in df_raw.columns:
            raise ValueError(f"La variable de segmentación '{segment_variable}' no existe.")

        df_raw[segment_variable] = df_raw[segment_variable].astype(str).str.strip()
        unique_segments = df_raw[segment_variable].unique()

        for segment in unique_segments:
            df_chunk = df_raw[df_raw[segment_variable] == segment].copy()
            try:
                if segment not in pmml_manager.models_mapping:
                    raise KeyError(f"El segmento '{segment}' carece de definición de modelo en el JSON.")

                if df_types is not None:
                    df_chunk_transformed = data_transformer(df_chunk, csv_schema_mapping)
                else:
                    pmml_native_schema = pmml_manager.get_pmml_schema(segment)
                    df_chunk_transformed = data_transformer(df_chunk, pmml_native_schema)

                df_chunk_scored = pmml_manager.score_segment(df_chunk_transformed, segment)
                df_chunk_scored["executed_segment"] = segment
                processed_segments_chunks.append(df_chunk_scored)
            except Exception as e:
                logger.error(f"Fallo crítico en segmento '{segment}': {str(e)}")
                raise e

    df_final_output = pd.concat(processed_segments_chunks, axis=0).sort_index()
    return df_final_output