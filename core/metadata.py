"""
core.metadata
=============
Auditoria estatica de un archivo PMML: ficha tecnica, esquema de variables,
transformaciones y arquitectura del modelo.

Dos correcciones de fondo respecto de la version anterior:

1. **Cobertura de tipos de modelo.** Antes se buscaba unicamente
   `.//MiningModel` para reconstruir el flujo, de modo que un `RegressionModel`,
   un `TreeModel` o un `Scorecard` (todos habituales en scorecards de riesgo)
   producian un diagrama vacio. Ahora se reconoce cualquier elemento de modelo
   del estandar PMML 4.x.

2. **Deteccion del target.** Antes se adivinaba por nombre contra una lista fija
   ('target', 'clase', ...), asi que un modelo con la variable objetivo llamada
   'incumplimiento_12m' quedaba sin target y esa variable se reportaba
   incorrectamente como predictor. Ahora se lee del `MiningSchema` por
   `usageType="target"`, que es la fuente normativa.

El parseo es agnostico al namespace: se compara siempre por nombre local, de
forma que PMML 4.2, 4.3 y 4.4 se procesan con el mismo codigo.
"""

from __future__ import annotations

import io
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

# Elementos que el estandar PMML define como modelos ejecutables.
ELEMENTOS_MODELO = {
    "AnomalyDetectionModel", "AssociationModel", "BayesianNetworkModel",
    "BaselineModel", "ClusteringModel", "GaussianProcessModel",
    "GeneralRegressionModel", "MiningModel", "NaiveBayesModel",
    "NearestNeighborModel", "NeuralNetwork", "RegressionModel",
    "RuleSetModel", "SequenceModel", "Scorecard", "SupportVectorMachineModel",
    "TextModel", "TimeSeriesModel", "TreeModel",
}

# Traduccion a lenguaje de negocio para la ficha tecnica.
NOMBRE_LEGIBLE = {
    "MiningModel": "Ensamble / Modelo compuesto",
    "RegressionModel": "Regresión (lineal o logística)",
    "GeneralRegressionModel": "Regresión generalizada (GLM)",
    "TreeModel": "Árbol de decisión",
    "Scorecard": "Scorecard de puntuación",
    "NeuralNetwork": "Red neuronal",
    "SupportVectorMachineModel": "Máquina de vectores de soporte",
    "NaiveBayesModel": "Naive Bayes",
    "ClusteringModel": "Segmentación (clustering)",
    "RuleSetModel": "Conjunto de reglas",
    "NearestNeighborModel": "K vecinos más cercanos",
}


@dataclass
class MetadatosPMML:
    """Representacion estructurada del contenido de un archivo PMML."""

    ficha: Dict[str, Any] = field(default_factory=dict)
    entradas: List[dict] = field(default_factory=list)
    salidas: List[dict] = field(default_factory=list)
    objetivos: List[dict] = field(default_factory=list)
    transformaciones: List[dict] = field(default_factory=list)
    arquitectura: List[dict] = field(default_factory=list)
    log: str = ""
    error: Optional[str] = None


def _local(etiqueta: str) -> str:
    """Nombre local de una etiqueta XML, descartando el namespace."""
    return etiqueta.rsplit("}", 1)[-1]


def _hijos(nodo, nombre: str):
    """Hijos directos con el nombre local indicado."""
    return [h for h in list(nodo) if _local(h.tag) == nombre]


def _buscar_todos(nodo, nombre: str):
    """Descendientes (a cualquier profundidad) con el nombre local indicado."""
    return [n for n in nodo.iter() if _local(n.tag) == nombre]


def _primero(nodo, nombre: str):
    encontrados = _hijos(nodo, nombre)
    return encontrados[0] if encontrados else None


def analizar_pmml(contenido: bytes | str) -> MetadatosPMML:
    """Parsea un PMML y devuelve su metadata estructurada."""
    metadatos = MetadatosPMML()
    buffer = io.StringIO()

    def registrar(mensaje: str = "") -> None:
        buffer.write(mensaje + "\n")

    registrar("=" * 74)
    registrar("   AUDITORÍA ESTÁTICA DE MODELO PMML — RIESGO DE CRÉDITO")
    registrar("=" * 74)
    registrar()

    try:
        if isinstance(contenido, bytes):
            raiz = ET.fromstring(contenido)
        else:
            raiz = ET.fromstring(contenido.encode("utf-8"))
    except ET.ParseError as exc:
        metadatos.error = f"El archivo no es un XML válido: {exc}"
        metadatos.log = buffer.getvalue() + metadatos.error
        return metadatos

    # ---------------------------------------------------------------- ficha
    version_pmml = raiz.get("version", "no declarada")
    cabecera = _primero(raiz, "Header")
    aplicacion = version_app = fecha = "No especificado"
    copyright_txt = descripcion = ""

    if cabecera is not None:
        nodo_app = _primero(cabecera, "Application")
        if nodo_app is not None:
            aplicacion = nodo_app.get("name", "No especificado")
            version_app = nodo_app.get("version", "No especificada")
        nodo_fecha = _primero(cabecera, "Timestamp")
        if nodo_fecha is not None and nodo_fecha.text:
            fecha = nodo_fecha.text.strip()
        copyright_txt = cabecera.get("copyright", "") or ""
        descripcion = cabecera.get("description", "") or ""

    metadatos.ficha = {
        "Versión PMML": version_pmml,
        "Aplicación exportadora": aplicacion,
        "Versión del exportador": version_app,
        "Fecha de compilación": fecha,
        "Copyright": copyright_txt or "—",
        "Descripción": descripcion or "—",
    }

    registrar("--- [1] FICHA TÉCNICA ---")
    for clave, valor in metadatos.ficha.items():
        registrar(f"  • {clave}: {valor}")
    registrar()

    # -------------------------------------------- diccionario de datos base
    tipos_declarados: Dict[str, dict] = {}
    diccionario = _primero(raiz, "DataDictionary")
    if diccionario is not None:
        for campo in _hijos(diccionario, "DataField"):
            nombre = campo.get("name", "")
            valores = [v.get("value") for v in _hijos(campo, "Value")]
            intervalos = _hijos(campo, "Interval")
            dominio = ""
            if valores:
                muestra = ", ".join(str(v) for v in valores[:6])
                dominio = muestra + (" ..." if len(valores) > 6 else "")
            elif intervalos:
                izq = intervalos[0].get("leftMargin", "-inf")
                der = intervalos[0].get("rightMargin", "+inf")
                dominio = f"[{izq}, {der}]"
            tipos_declarados[nombre] = {
                "optype": campo.get("optype", "—"),
                "dataType": campo.get("dataType", "—"),
                "dominio": dominio or "—",
            }

    # --------------------------------- modelos, esquema de minado y target
    nodos_modelo = [n for n in raiz.iter() if _local(n.tag) in ELEMENTOS_MODELO]
    nombres_target: List[str] = []
    activas: List[str] = []

    for nodo in nodos_modelo:
        esquema = _primero(nodo, "MiningSchema")
        if esquema is None:
            continue
        for campo in _hijos(esquema, "MiningField"):
            nombre = campo.get("name", "")
            uso = (campo.get("usageType") or "active").lower()
            if uso in ("target", "predicted"):
                if nombre not in nombres_target:
                    nombres_target.append(nombre)
            elif uso == "active" and nombre not in activas:
                activas.append(nombre)

    # Fallback: modelos sin MiningSchema utilizable -> todo el diccionario.
    if not activas:
        activas = [n for n in tipos_declarados if n not in nombres_target]

    for nombre in activas:
        info = tipos_declarados.get(nombre, {})
        metadatos.entradas.append(
            {
                "Variable de entrada": nombre,
                "Tipo operativo": info.get("optype", "—"),
                "Tipo de dato": info.get("dataType", "—"),
                "Dominio declarado": info.get("dominio", "—"),
            }
        )

    for nombre in nombres_target:
        info = tipos_declarados.get(nombre, {})
        metadatos.objetivos.append(
            {
                "Variable objetivo": nombre,
                "Tipo operativo": info.get("optype", "—"),
                "Tipo de dato": info.get("dataType", "—"),
                "Categorías": info.get("dominio", "—"),
            }
        )

    metadatos.ficha["Variable objetivo"] = (
        ", ".join(nombres_target) if nombres_target else "No declarada"
    )

    registrar("--- [2] ESQUEMA DE VARIABLES ---")
    registrar(f"  Predictores activos : {len(metadatos.entradas)}")
    registrar(f"  Variable(s) objetivo: {metadatos.ficha['Variable objetivo']}")
    registrar()

    # ------------------------------------------------------------- salidas
    for salida in _buscar_todos(raiz, "OutputField"):
        metadatos.salidas.append(
            {
                "Variable de salida": salida.get("name", ""),
                "Característica": salida.get("feature", "predictedValue"),
                "Valor asociado": salida.get("value", "—"),
                "Tipo de dato": salida.get("dataType", "—"),
            }
        )

    # ----------------------------------------------------- transformaciones
    for derivado in _buscar_todos(raiz, "DerivedField"):
        expresion = "—"
        for hijo in list(derivado):
            etiqueta = _local(hijo.tag)
            if etiqueta == "FieldRef":
                expresion = f"Referencia directa a «{hijo.get('field')}»"
            elif etiqueta == "Apply":
                expresion = f"Función «{hijo.get('function', '?')}»"
            elif etiqueta == "NormContinuous":
                expresion = f"Normalización continua de «{hijo.get('field', '?')}»"
            elif etiqueta == "NormDiscrete":
                expresion = f"Indicadora de «{hijo.get('field', '?')}» = {hijo.get('value', '?')}"
            elif etiqueta == "Discretize":
                expresion = f"Discretización de «{hijo.get('field', '?')}»"
            elif etiqueta == "MapValues":
                expresion = "Mapeo de valores por tabla"
            if expresion != "—":
                break
        metadatos.transformaciones.append(
            {
                "Variable derivada": derivado.get("name", ""),
                "Definición": expresion,
                "Tipo de dato": derivado.get("dataType", "—"),
            }
        )

    # ------------------------------------------------------- arquitectura
    def recorrer(nodo, nivel: int = 1, etiqueta: str = "Modelo principal") -> None:
        tipo = _local(nodo.tag)
        algoritmo = nodo.get("algorithmName") or NOMBRE_LEGIBLE.get(tipo, tipo)
        funcion = nodo.get("functionName", "—")

        metadatos.arquitectura.append(
            {
                "nivel": nivel,
                "instancia": etiqueta,
                "tipo": tipo,
                "algoritmo": algoritmo,
                "funcion": funcion,
            }
        )
        registrar(f"  {'  ' * (nivel - 1)}└─ Nivel {nivel} | {etiqueta} | {tipo} ({funcion})")

        segmentacion = _primero(nodo, "Segmentation")
        if segmentacion is None:
            return

        metodo = segmentacion.get("multipleModelMethod", "desconocido")
        segmentos = _hijos(segmentacion, "Segment")

        # Los ensambles grandes (GBM, random forest) se colapsan en un solo
        # nodo: dibujar 500 arboles no aporta informacion y hace ilegible el
        # diagrama.
        if len(segmentos) > 12:
            metadatos.arquitectura.append(
                {
                    "nivel": nivel + 1,
                    "instancia": f"Ensamble de {len(segmentos)} submodelos",
                    "tipo": "Segmentation",
                    "algoritmo": f"Combinación por «{metodo}»",
                    "funcion": metodo,
                }
            )
            registrar(
                f"  {'  ' * nivel}└─ Nivel {nivel + 1} | Ensamble de "
                f"{len(segmentos)} submodelos (método: {metodo})"
            )
            return

        for indice, segmento in enumerate(segmentos, start=1):
            for hijo in list(segmento):
                if _local(hijo.tag) in ELEMENTOS_MODELO:
                    identificador = segmento.get("id", str(indice))
                    recorrer(hijo, nivel + 1, f"Segmento {identificador}")
                    break

    registrar("--- [3] ARQUITECTURA DEL MODELO ---")
    raices_modelo = [n for n in list(raiz) if _local(n.tag) in ELEMENTOS_MODELO]
    if not raices_modelo:
        # PMML con el modelo anidado bajo otro contenedor.
        raices_modelo = nodos_modelo[:1]

    for nodo in raices_modelo:
        recorrer(nodo)

    if not metadatos.arquitectura:
        registrar("  (No se identificó ningún elemento de modelo ejecutable)")

    registrar()
    registrar("--- [4] RESUMEN ---")
    registrar(f"  Predictores        : {len(metadatos.entradas)}")
    registrar(f"  Salidas declaradas : {len(metadatos.salidas)}")
    registrar(f"  Transformaciones   : {len(metadatos.transformaciones)}")
    registrar(f"  Capas de modelo    : {len(metadatos.arquitectura)}")

    metadatos.log = buffer.getvalue()
    return metadatos


def construir_mermaid(metadatos: MetadatosPMML) -> str:
    """Genera el codigo Mermaid del diagrama de arquitectura."""
    lineas = ["graph TD"]
    lineas.append('    ENTRADA(["Ingesta de variables"])')

    nodo_previo = "ENTRADA"
    if metadatos.transformaciones:
        etiqueta = f"Transformaciones<br/>({len(metadatos.transformaciones)} derivadas)"
        lineas.append(f'    TRANSF["{etiqueta}"]')
        lineas.append(f"    {nodo_previo} --> TRANSF")
        nodo_previo = "TRANSF"

    for indice, paso in enumerate(metadatos.arquitectura):
        identificador = f"M{indice}"
        instancia = str(paso.get("instancia", "")).replace('"', "'")
        algoritmo = str(paso.get("algoritmo", "")).replace('"', "'")
        lineas.append(f'    {identificador}["{instancia}<br/><i>{algoritmo}</i>"]')
        lineas.append(f"    {nodo_previo} --> {identificador}")
        nodo_previo = identificador

    salidas = len(metadatos.salidas)
    lineas.append(f'    SALIDA(["Scoring y salidas<br/>({salidas} campos)"])')
    lineas.append(f"    {nodo_previo} --> SALIDA")

    # Paleta corporativa aplicada al diagrama.
    lineas.append("    classDef io fill:#072146,stroke:#072146,color:#FFFFFF;")
    lineas.append("    classDef proc fill:#49A5E6,stroke:#1464A5,color:#072146;")
    lineas.append("    classDef modelo fill:#1464A5,stroke:#072146,color:#FFFFFF;")
    lineas.append("    class ENTRADA,SALIDA io;")
    if metadatos.transformaciones:
        lineas.append("    class TRANSF proc;")
    if metadatos.arquitectura:
        ids = ",".join(f"M{i}" for i in range(len(metadatos.arquitectura)))
        lineas.append(f"    class {ids} modelo;")

    return "\n".join(lineas)
