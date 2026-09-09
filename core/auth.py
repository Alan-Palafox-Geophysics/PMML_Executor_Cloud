"""
core.auth
=========
Autenticacion y control de acceso por rol.

Las credenciales viven en `st.secrets`, nunca en el codigo fuente. Se admiten
dos formatos:

Formato con roles (recomendado):

    [usuarios.rt_bistro]
    password = "..."
    rol      = "admin"
    nombre   = "Administrador"

Formato simple (compatibilidad con despliegues anteriores):

    [credenciales]
    rt_bistro = "..."

En el formato simple todos los usuarios reciben el rol `analista`.
"""

from __future__ import annotations

import hmac
from dataclasses import dataclass, field
from typing import Dict, Optional, Set

import streamlit as st

# Permisos por rol. Cada permiso habilita una capacidad concreta de la app.
PERMISOS: Dict[str, Set[str]] = {
    # Perfil administrador: acceso completo, incluido el diagnostico tecnico
    # del entorno (rutas del sistema, version de la JVM) y la gestion de
    # parametros avanzados de ejecucion.
    "admin": {
        "ejecucion", "conciliacion", "analisis", "roadmap",
        "diagnostico", "opciones_avanzadas",
    },
    # Perfil analista: operacion completa sin detalles de infraestructura.
    "analista": {
        "ejecucion", "conciliacion", "analisis", "roadmap",
        "opciones_avanzadas",
    },
    # Perfil consulta: solo lectura de resultados ya generados.
    "consulta": {"analisis", "roadmap"},
}

ETIQUETA_ROL = {
    "admin": "Administrador",
    "analista": "Analista",
    "consulta": "Consulta",
}


@dataclass
class Usuario:
    """Identidad autenticada dentro de la sesion."""

    id: str
    rol: str = "analista"
    nombre: str = ""
    permisos: Set[str] = field(default_factory=set)

    def puede(self, permiso: str) -> bool:
        return permiso in self.permisos

    @property
    def etiqueta_rol(self) -> str:
        return ETIQUETA_ROL.get(self.rol, self.rol.capitalize())


def _leer_directorio() -> Dict[str, dict]:
    """
    Normaliza el directorio de usuarios definido en los secrets.

    Devuelve {id_usuario: {password, rol, nombre}} independientemente del
    formato usado en `secrets.toml`.
    """
    directorio: Dict[str, dict] = {}

    # Formato con roles.
    try:
        usuarios = dict(st.secrets.get("usuarios", {}))
    except Exception:
        usuarios = {}

    for identificador, datos in usuarios.items():
        try:
            registro = dict(datos)
        except Exception:
            continue
        rol = str(registro.get("rol", "analista")).strip().lower()
        directorio[str(identificador).strip()] = {
            "password": str(registro.get("password", "")),
            "rol": rol if rol in PERMISOS else "analista",
            "nombre": str(registro.get("nombre", identificador)),
        }

    # Formato simple, solo para los usuarios que no aparezcan ya arriba.
    try:
        credenciales = dict(st.secrets.get("credenciales", {}))
    except Exception:
        credenciales = {}

    for identificador, contrasena in credenciales.items():
        clave = str(identificador).strip()
        if clave not in directorio:
            directorio[clave] = {
                "password": str(contrasena),
                "rol": "analista",
                "nombre": clave,
            }

    return directorio


def hay_credenciales_configuradas() -> bool:
    """True si existe al menos un usuario definido en los secrets."""
    return bool(_leer_directorio())


def autenticar(usuario: str, contrasena: str) -> Optional[Usuario]:
    """
    Valida las credenciales y devuelve el `Usuario` autenticado, o None.

    La comparacion usa `hmac.compare_digest` en lugar del operador `==`: el
    tiempo de ejecucion no depende de cuantos caracteres coinciden, de modo que
    no se filtra informacion sobre la contrasena por medicion de tiempos.
    """
    directorio = _leer_directorio()
    registro = directorio.get(str(usuario).strip())

    # Se comparan bytes, no str: `hmac.compare_digest` rechaza cadenas con
    # caracteres no ASCII, y una contrasena con acentos o «ñ» es perfectamente
    # legitima.
    entrada = (contrasena or "").encode("utf-8")

    if registro is None:
        # Comparacion ficticia para que el tiempo de respuesta sea equivalente
        # tanto si el usuario existe como si no.
        hmac.compare_digest(b"contrasena-inexistente", entrada)
        return None

    if not hmac.compare_digest(registro["password"].encode("utf-8"), entrada):
        return None

    rol = registro["rol"]
    return Usuario(
        id=str(usuario).strip(),
        rol=rol,
        nombre=registro["nombre"],
        permisos=set(PERMISOS.get(rol, PERMISOS["analista"])),
    )
