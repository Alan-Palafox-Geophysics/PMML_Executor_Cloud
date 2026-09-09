"""
core.jvm
========
Arranque robusto de la JVM y gestion del ciclo de vida de los evaluadores JPMML.

Por que existe este modulo
--------------------------
`jpmml_evaluator` usa por defecto el backend **jpype**, que arranca una JVM
*embebida* dentro del proceso de Python. Esto impone tres restricciones que la
version original de la app no contemplaba y que son la causa mas comun de
fallos en Streamlit Community Cloud:

1. La JVM solo puede arrancarse UNA vez por proceso. Streamlit re-ejecuta el
   script completo en cada interaccion, asi que hay que memoizar el arranque.
2. JPype necesita localizar `libjvm.so`. En Streamlit Cloud el JRE se instala
   via `packages.txt` pero **JAVA_HOME no queda definido**, por lo que hay que
   descubrirlo a mano antes de importar jpype.
3. Construir un evaluador re-parsea el PMML y re-inicializa objetos Java. Es
   caro (segundos en modelos de ensamble), asi que se cachea por hash de
   contenido del modelo.

Todo el acceso a Java del resto de la aplicacion pasa por aqui.
"""

from __future__ import annotations

import glob
import hashlib
import os
import shutil
import subprocess
import threading
from dataclasses import dataclass, field
from typing import Any, Optional

# Candidatos de JAVA_HOME ordenados por preferencia. Streamlit Cloud corre sobre
# Debian, donde openjdk queda bajo /usr/lib/jvm/java-<ver>-openjdk-<arch>.
_RUTAS_JVM_CANDIDATAS = (
    "/usr/lib/jvm/java-17-openjdk-amd64",
    "/usr/lib/jvm/java-17-openjdk-arm64",
    "/usr/lib/jvm/java-21-openjdk-amd64",
    "/usr/lib/jvm/java-21-openjdk-arm64",
    "/usr/lib/jvm/default-java",
    "/usr/lib/jvm/java-11-openjdk-amd64",
)

_candado_arranque = threading.Lock()


@dataclass
class EstadoJVM:
    """Resultado del arranque de la JVM, apto para mostrar en la interfaz."""

    disponible: bool
    java_home: Optional[str] = None
    version_java: Optional[str] = None
    version_jpmml: Optional[str] = None
    heap_maximo_mb: Optional[int] = None
    detalle_error: Optional[str] = None
    diagnostico: list[str] = field(default_factory=list)


def _descubrir_java_home() -> Optional[str]:
    """Localiza un JAVA_HOME utilizable sin depender de variables de entorno."""
    # 1) Respetar un JAVA_HOME ya definido si realmente contiene una JVM.
    java_home_actual = os.environ.get("JAVA_HOME")
    if java_home_actual and _tiene_libjvm(java_home_actual):
        return java_home_actual

    # 2) JRE empaquetado como wheel de PyPI (jdk4py).
    #
    #    Esta es la via preferente en Streamlit Cloud. Instalar Java por
    #    `packages.txt` depende de que `apt-get update` termine sin errores, y
    #    la imagen de Cloud mezcla repositorios Debian: cuando el Release file
    #    de alguno caduca, apt devuelve codigo distinto de cero y el despliegue
    #    se cae ANTES de instalar nada. Al venir el runtime dentro de un wheel,
    #    el problema desaparece: se instala con pip como cualquier dependencia.
    try:
        import jdk4py  # noqa: PLC0415

        ruta_jdk4py = str(jdk4py.JAVA_HOME)
        if _tiene_libjvm(ruta_jdk4py):
            return ruta_jdk4py
    except Exception:
        pass

    # 3) Rutas conocidas de Debian/Ubuntu (instalacion por apt).
    for ruta in _RUTAS_JVM_CANDIDATAS:
        if _tiene_libjvm(ruta):
            return ruta

    # 4) Cualquier openjdk instalado bajo /usr/lib/jvm.
    for ruta in sorted(glob.glob("/usr/lib/jvm/*"), reverse=True):
        if _tiene_libjvm(ruta):
            return ruta

    # 5) Derivar desde el ejecutable `java` que este en PATH.
    ejecutable = shutil.which("java")
    if ejecutable:
        real = os.path.realpath(ejecutable)  # /usr/lib/jvm/<jdk>/bin/java
        candidato = os.path.dirname(os.path.dirname(real))
        if _tiene_libjvm(candidato):
            return candidato

    return None


def _tiene_libjvm(java_home: str) -> bool:
    """True si la ruta contiene una biblioteca libjvm cargable por JPype."""
    if not java_home or not os.path.isdir(java_home):
        return False
    patrones = (
        os.path.join(java_home, "lib", "server", "libjvm.so"),
        os.path.join(java_home, "lib", "*", "server", "libjvm.so"),
        os.path.join(java_home, "jre", "lib", "*", "server", "libjvm.so"),
        os.path.join(java_home, "lib", "server", "libjvm.dylib"),
        os.path.join(java_home, "bin", "server", "jvm.dll"),
    )
    return any(glob.glob(p) for p in patrones)


def _leer_version_java(java_home: str) -> Optional[str]:
    """Obtiene la version del runtime para mostrarla como diagnostico."""
    binario = os.path.join(java_home, "bin", "java")
    if not os.path.isfile(binario):
        binario = shutil.which("java") or ""
    if not binario:
        return None
    try:
        proceso = subprocess.run(
            [binario, "-version"], capture_output=True, text=True, timeout=25
        )
        # `java -version` escribe en stderr por diseno historico.
        salida = (proceso.stderr or proceso.stdout).strip().splitlines()
        return salida[0].strip() if salida else None
    except Exception:
        return None


def _memoria_total_mb() -> int:
    """RAM total del contenedor, leida de /proc/meminfo."""
    try:
        with open("/proc/meminfo", "r", encoding="utf-8") as fichero:
            for linea in fichero:
                if linea.startswith("MemTotal:"):
                    return int(linea.split()[1]) // 1024
    except Exception:
        pass
    return 1024  # Supuesto conservador: plan gratuito de Streamlit Cloud.


def heap_objetivo_mb() -> int:
    """
    Calcula el tamano maximo del heap de la JVM.

    Sin un `-Xmx` explicito, la JVM se autoasigna 1/4 de la RAM fisica. En un
    contenedor de 1 GB eso son unos 256 MB, insuficiente para evaluar lotes
    grandes: de ahi el `OutOfMemoryError: Java heap space`.

    Tampoco conviene subirlo sin limite. Python y pandas comparten la misma
    memoria del contenedor, y si la JVM se la come el proceso entero muere por
    OOM del sistema operativo, que es peor: en lugar de una excepcion
    recuperable, la aplicacion se reinicia y se pierde la sesion.

    Se reserva por tanto en torno al 45% de la RAM, dejando el resto para el
    dataframe de pandas y el propio runtime.
    """
    override = os.environ.get("PMML_JVM_HEAP_MB", "").strip()
    if override.isdigit():
        return max(int(override), 128)

    total = _memoria_total_mb()
    return max(256, min(int(total * 0.45), 2048))


def _opciones_jvm() -> list[str]:
    """Parametros de arranque de la JVM ajustados a un contenedor pequeno."""
    heap = heap_objetivo_mb()
    return [
        f"-Xmx{heap}m",
        "-Xms64m",
        # SerialGC tiene mucha menos huella que G1 en heaps pequenos: G1
        # reserva estructuras auxiliares que en 256-512 MB pesan demasiado.
        "-XX:+UseSerialGC",
        # Evita que el metaspace crezca sin control al cargar muchos modelos.
        "-XX:MaxMetaspaceSize=192m",
        # Pila mas pequena por hilo: los evaluadores PMML no recursan hondo.
        "-Xss512k",
        # Devuelve memoria libre al sistema operativo en lugar de retenerla.
        "-XX:+ShrinkHeapInSteps",
        "-Djava.awt.headless=true",
    ]


def iniciar_jvm() -> EstadoJVM:
    """
    Arranca la JVM de forma idempotente y devuelve un estado inspeccionable.

    Nunca lanza excepcion: si Java no esta disponible se devuelve un `EstadoJVM`
    con `disponible=False` y un diagnostico legible, para que la interfaz pueda
    mostrar un mensaje util en lugar de un stack trace.
    """
    diagnostico: list[str] = []

    java_home = _descubrir_java_home()
    if java_home is None:
        diagnostico.append(
            "No se encontro ninguna JVM. Verifica que 'jdk4py' figure en "
            "requirements.txt y que la instalacion de dependencias haya "
            "terminado sin errores."
        )
        return EstadoJVM(
            disponible=False,
            detalle_error="JAVA_HOME no localizable",
            diagnostico=diagnostico,
        )

    # JPype lee JAVA_HOME al importar: hay que fijarlo ANTES del import.
    os.environ["JAVA_HOME"] = java_home
    diagnostico.append(f"JAVA_HOME resuelto en: {java_home}")

    with _candado_arranque:
        try:
            import jpype  # noqa: PLC0415  (import diferido intencional)
            import jpmml_evaluator  # noqa: PLC0415

            heap = heap_objetivo_mb()

            if not jpype.isJVMStarted():
                # La JVM se arranca aqui, no en `JPypeBackend.ensureJVM()`, que
                # la crearia sin parametros de memoria. Se replica su classpath
                # para que los JAR de JPMML sigan disponibles.
                from jpmml_evaluator import _classpath  # noqa: PLC0415

                jpype.startJVM(*_opciones_jvm(), classpath=_classpath(user_classpath=[]))
                diagnostico.append(
                    f"JVM arrancada con heap maximo de {heap} MB "
                    f"(RAM del contenedor: {_memoria_total_mb()} MB)."
                )
            else:
                diagnostico.append("JVM ya estaba activa; se reutiliza la instancia.")

            # Deja el backend listo (importa las clases auxiliares de JPMML).
            from jpmml_evaluator.jpype import JPypeBackend  # noqa: PLC0415

            JPypeBackend.ensureJVM()

            return EstadoJVM(
                disponible=True,
                java_home=java_home,
                version_java=_leer_version_java(java_home),
                version_jpmml=getattr(jpmml_evaluator, "__version__", "0.16.0"),
                heap_maximo_mb=heap,
                diagnostico=diagnostico,
            )
        except Exception as exc:  # pragma: no cover - depende del entorno
            diagnostico.append(f"Fallo al inicializar JPype: {exc}")
            return EstadoJVM(
                disponible=False,
                java_home=java_home,
                detalle_error=str(exc),
                diagnostico=diagnostico,
            )


def memoria_java() -> Optional[dict]:
    """
    Estado actual del heap de la JVM, en MB.

    Permite mostrar el consumo real en la interfaz en lugar de esperar a que
    reviente con un OutOfMemoryError.
    """
    try:
        import jpype  # noqa: PLC0415

        if not jpype.isJVMStarted():
            return None
        runtime = jpype.JClass("java.lang.Runtime").getRuntime()
        maxima = int(runtime.maxMemory()) // (1024 * 1024)
        total = int(runtime.totalMemory()) // (1024 * 1024)
        libre = int(runtime.freeMemory()) // (1024 * 1024)
        return {
            "maxima_mb": maxima,
            "reservada_mb": total,
            "en_uso_mb": total - libre,
            "uso_pct": round(100.0 * (total - libre) / max(maxima, 1), 1),
        }
    except Exception:
        return None


def liberar_memoria_java() -> bool:
    """
    Solicita a la JVM que recolecte los objetos ya inalcanzables.

    `System.gc()` es una sugerencia, no una orden, pero tras procesar un lote
    grande libera de forma fiable las estructuras intermedias del evaluador.
    """
    try:
        import jpype  # noqa: PLC0415

        if not jpype.isJVMStarted():
            return False
        jpype.JClass("java.lang.System").gc()
        return True
    except Exception:
        return False


def hash_contenido(datos: bytes) -> str:
    """Huella estable del contenido de un PMML, usada como clave de cache."""
    return hashlib.sha256(datos).hexdigest()


def construir_evaluador(pmml_bytes: bytes) -> Any:
    """
    Construye un evaluador JPMML a partir del contenido binario del modelo.

    Se trabaja con bytes (no rutas) por dos razones: permite cachear por
    contenido y evita depender de archivos temporales que en un entorno
    multiusuario pueden colisionar o desaparecer entre reruns.
    """
    estado = iniciar_jvm()
    if not estado.disponible:
        raise RuntimeError(
            "No hay una JVM disponible para evaluar el modelo PMML. "
            f"Detalle: {estado.detalle_error}"
        )

    from jpmml_evaluator import make_evaluator  # noqa: PLC0415

    # `lax=False` mantiene las validaciones de esquema del modelo, que en un
    # contexto de riesgo de credito son deseables: preferimos fallar temprano
    # antes que puntuar con un esquema inconsistente.
    evaluador = make_evaluator(pmml_bytes, backend="jpype", lax=False)
    return evaluador
