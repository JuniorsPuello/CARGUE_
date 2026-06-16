"""
Configuración central del proyecto.

Detecta automáticamente la ruta de Tesseract-OCR y permite persistir la ruta
elegida por el usuario en 'config.json'.

El renderizado PDF->imagen lo hace pypdfium2 (no requiere Poppler), por lo que
el único binario externo necesario es Tesseract.

Orden de prioridad para la ruta de Tesseract:
    1. Valor guardado en config.json (si el usuario lo configuró en la interfaz).
    2. Ejecutable disponible en el PATH del sistema.
    3. Rutas de instalación comunes en Windows.
"""

import os
import json
import shutil

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE_DIR, "config.json")

# Rutas de instalación habituales de Tesseract en Windows.
RUTAS_TESSERACT = [
    r"C:\Program Files\Tesseract-OCR\tesseract.exe",
    r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
]


def _primera_ruta_existente(rutas):
    for r in rutas:
        if r and os.path.exists(r):
            return r
    return None


def _detectar_tesseract():
    en_path = shutil.which("tesseract")
    if en_path:
        return en_path
    return _primera_ruta_existente(RUTAS_TESSERACT)


def cargar_config():
    """Devuelve dict {'tesseract_cmd': ...} con autodetección."""
    cfg = {"tesseract_cmd": None}

    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                guardado = json.load(f)
            valor = guardado.get("tesseract_cmd")
            if valor and os.path.exists(valor):
                cfg["tesseract_cmd"] = valor
        except (json.JSONDecodeError, OSError):
            pass  # config corrupta: se ignora y se autodetecta

    if not cfg["tesseract_cmd"]:
        cfg["tesseract_cmd"] = _detectar_tesseract()

    return cfg


def guardar_config(cfg):
    """Persiste la ruta elegida por el usuario en config.json."""
    datos = {"tesseract_cmd": cfg.get("tesseract_cmd") or ""}
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(datos, f, indent=2, ensure_ascii=False)
