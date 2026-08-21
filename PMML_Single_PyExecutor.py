import os
import gc
import logging
from typing import Dict, Any, Optional, List, Tuple
import pandas as pd
from jpmml_evaluator import make_evaluator

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("Single_PMML_Scoring_Engine")


def data_reader(
    data_path: str, types_path: Optional[str] = None
) -> Tuple[pd.DataFrame, Optional[pd.DataFrame]]:
    if not os.path.exists(data_path):
        raise FileNotFoundError(f"No se encontró el dataset en: {data_path}")
    df_data = pd.read_csv(data_path, dtype=str)
    
    df_types = None
    if types_path:
        if not os.path.exists(types_path):
            raise FileNotFoundError(f"No se encontró el archivo de tipos en: {types_path}")
        df_types = pd.read_csv(types_path)
        
    return df_data, df_types


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


class SinglePMMLManager:
    def __init__(self, pmml_path: str):
        self.pmml_path = pmml_path
        self.model = None
        self._type_fallback_map = {
            "double": "float64",
            "float": "float32",
            "integer": "int64",
            "int": "int64",
            "string": "object",
            "boolean": "bool"
        }
        self._preload_model()

    def _preload_model(self) -> None:
        if not os.path.exists(self.pmml_path):
            raise FileNotFoundError(f"Archivo PMML no encontrado: {self.pmml_path}")
        self.model = make_evaluator(self.pmml_path)

    def get_pmml_schema(self) -> Dict[str, str]:
        schema = {}
        for field in self.model.getInputFields():
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

    def get_input_order(self) -> List[str]:
        return [str(field.getName()) if hasattr(field, 'getName') else str(field.name) for field in self.model.getInputFields()]

    def score(self, df_input: pd.DataFrame) -> pd.DataFrame:
        input_order = self.get_input_order()
        missing_cols = [col for col in input_order if col not in df_input.columns]
        if missing_cols:
            raise ValueError(f"El dataset carece de variables requeridas por el PMML: {missing_cols}")

        df_scoring_input = df_input[input_order]
        df_predictions = self.model.evaluateAll(df_scoring_input)

        if isinstance(df_predictions, pd.Series):
            df_predictions = pd.DataFrame(df_predictions, columns=["prediction"])

        df_predictions.index = df_input.index
        df_scored_output = pd.concat([df_input, df_predictions], axis=1)
        
        return df_scored_output


def PMML_Single_Executor(
    data_path: str, pmml_path: str, types_path: Optional[str] = None, chunk_size: int = 1000
) -> pd.DataFrame:
    df_raw, df_types = data_reader(data_path, types_path)
    pmml_manager = SinglePMMLManager(pmml_path)
    
    try:
        if df_types is not None:
            csv_schema_mapping = dict(zip(df_types.iloc[:, 0], df_types.iloc[:, 1]))
            df_transformed = data_transformer(df_raw, csv_schema_mapping)
        else:
            pmml_native_schema = pmml_manager.get_pmml_schema()
            df_transformed = data_transformer(df_raw, pmml_native_schema)

        del df_raw
        gc.collect()

        total_rows = len(df_transformed)
        if total_rows > chunk_size:
            logger.info(f"Dataset con {total_rows} registros supera el umbral de {chunk_size}. Evaluando en chunks...")
            chunks_results = []
            for start_idx in range(0, total_rows, chunk_size):
                df_chunk = df_transformed.iloc[start_idx : start_idx + chunk_size].copy()
                df_scored_chunk = pmml_manager.score(df_chunk)
                chunks_results.append(df_scored_chunk)
                del df_chunk, df_scored_chunk
                gc.collect()
            
            df_scored = pd.concat(chunks_results, axis=0)
            del chunks_results
            gc.collect()
        else:
            df_scored = pmml_manager.score(df_transformed)

        return df_scored
    except Exception as e:
        logger.error(f"Fallo crítico procesando el dataset: {str(e)}")
        raise e