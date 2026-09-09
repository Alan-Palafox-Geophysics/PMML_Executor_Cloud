# PMML Risk Workspace

Entorno de ejecución, conciliación y validación de modelos **PMML** para riesgo
de crédito, construido sobre Streamlit y el motor **JPMML** (Java).

---

## Qué hace

| Módulo | Función |
|---|---|
| **1.1 Auditoría de metadatos** | Radiografía estática del PMML: ficha técnica, esquema de variables, transformaciones y diagrama de arquitectura. Exporta documentación en `.md` y log en `.txt`. |
| **1.2 Scoring de modelo único** | Evalúa un PMML sobre un dataset, con tipado automático, validación de esquema y proceso por bloques. |
| **1.3 Scoring multimodelo** | Enruta cada registro al modelo que corresponde a su segmento según un JSON de configuración. |
| **2. Conciliación** | Cruza el scoring de Python con el de la plataforma de decisión (Power Curve) y un origen opcional de cifras de control. Reporta la tasa de emparejamiento. |
| **3. Análisis comparativo** | Métricas de concordancia (diferencia absoluta, RMSE, correlación), criterio de tolerancia explícito y diagnóstico gráfico de las desviaciones. |
| **4. Hoja de ruta** | Módulos analíticos previstos. |

---

## Requisitos

- Python **3.11**
- **Java 17** (JRE headless) — indispensable: JPMML es una librería Java
- Las dependencias fijadas en `requirements.txt`

---

## Instalación local

```bash
git clone <URL-DE-TU-REPOSITORIO>
cd pmml-risk-workspace

python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate

pip install -r requirements.txt

# Java (si no lo tienes)
#   Ubuntu/Debian : sudo apt install openjdk-17-jre-headless
#   macOS         : brew install openjdk@17
#   Windows       : instala Temurin 17 y define JAVA_HOME
```

Configura las credenciales de acceso:

```bash
cp .streamlit/secrets.toml.example .streamlit/secrets.toml
# edita el archivo y define tus usuarios
```

Arranca:

```bash
streamlit run app.py
```

---

## Estructura

```
pmml-risk-workspace/
├── app.py                      # Punto de entrada
├── requirements.txt            # Dependencias con versión fijada
├── packages.txt                # Paquetes de sistema (Java) para Streamlit Cloud
├── runtime.txt                 # Versión de Python
├── .streamlit/
│   ├── config.toml             # Tema corporativo
│   └── secrets.toml.example    # Plantilla de credenciales (NO subir el real)
├── core/                       # Lógica de negocio, sin dependencia de la UI
│   ├── jvm.py                  # Arranque de la JVM y caché de evaluadores
│   ├── data_utils.py           # Lectura y casteo robusto de datos
│   ├── pmml_engine.py          # Motor de scoring
│   └── metadata.py             # Auditoría estática del PMML
└── ui/                         # Capa de presentación
    ├── theme.py                # Paleta e identidad visual
    ├── components.py           # Componentes reutilizables
    └── tabs/                   # Una pestaña por archivo
```

> Los paquetes se llaman `core` y `ui`, no `app`. Tener `app.py` y una carpeta
> `app/` en la misma raíz hace ambiguo el import de `app` y obliga a parchear
> `sys.path` a mano.

---

## Formatos de entrada

### Dataset

CSV o Parquet. Los CSV se leen como texto y luego se convierten al tipo que
declara el PMML. Esto evita que pandas infiera mal y se pierdan ceros a la
izquierda en identificadores.

Se toleran automáticamente: enteros escritos como `35.0`, separadores de miles,
coma decimal, porcentajes, negativos en notación contable `(1234)` y codificación
Latin-1.

### Diccionario de tipos (opcional)

CSV de dos columnas para forzar un esquema distinto al del PMML:

```csv
variable,tipo
ingreso,double
edad,integer
segmento,string
```

### Configuración multimodelo

```json
{
  "pmml_files": {
    "SEGMENTO_A": "modelo_a.pmml",
    "SEGMENTO_B": "modelo_b.pmml"
  }
}
```

---

## Notas de diseño

**Tipado tolerante con traza.** Una columna problemática no aborta el proceso:
se convierte lo convertible, lo irrecuperable queda nulo y todo se registra en
un reporte de incidencias consultable desde la interfaz.

**Registros sin score.** Un PMML sin estrategia de imputación devuelve nulo
cuando falta un predictor obligatorio. La aplicación cuenta y advierte sobre
esos registros: sin ese aviso, salen del proceso sin decisión y nadie se entera.

**Tolerancia explícita en la comparación.** El análisis de desviaciones usa la
diferencia absoluta como métrica principal, no el error relativo. Con
probabilidades cercanas a cero —la cola buena de cualquier cartera— el error
relativo se dispara y oculta las desviaciones que sí importan.

**Sin archivos temporales.** Todo se procesa en memoria. Escribir temporales con
el nombre del archivo subido provoca colisiones entre sesiones concurrentes.

**Credenciales fuera del código.** Se leen de `st.secrets`, nunca del fuente.

---

## Solución de problemas

| Síntoma | Causa y solución |
|---|---|
| «Motor Java no disponible» | Falta `packages.txt` en la **raíz** del repositorio, o el despliegue no se reconstruyó. Usa *Reboot app* en Streamlit Cloud. |
| «No hay credenciales configuradas» | Falta la sección `[credenciales]` en los secrets. |
| «El dataset no contiene N variable(s)…» | El dataset no corresponde a ese modelo, o los nombres no coinciden exactamente (mayúsculas y acentos incluidos). |
| «Ningún valor de la variable de enrutamiento coincide…» | La columna de segmento elegida no es la correcta, o los identificadores del JSON no coinciden con los del dataset. |
| Tasa de emparejamiento baja en la conciliación | Llave primaria equivocada o prefijo mal configurado. Revisa el paso 2.2. |
| La app se queda sin memoria | Reduce el tamaño de bloque en *Opciones avanzadas*. El plan gratuito de Streamlit Cloud ofrece ~1 GB de RAM. |

---

## Seguridad

- `.streamlit/secrets.toml` está en `.gitignore`. **Nunca** lo subas al repositorio.
- `.gitignore` excluye `*.csv`, `*.parquet` y `*.xlsx` para evitar subir datos de
  cartera por accidente. Si necesitas versionar datasets de ejemplo, colócalos
  en `ejemplos/` (ya está exceptuado) o ajusta la regla.
- Si el repositorio es público, cualquiera puede leer el código: mantén ahí solo
  lógica, nunca datos ni credenciales.
