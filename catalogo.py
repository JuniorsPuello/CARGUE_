"""
Catálogo de mapeos (módulo/operación -> tema, subtema, ley).

Los valores viven embebidos como respaldo, pero pueden **editarse sin tocar
código** en 'catalogo.csv' (abrible con Excel). Columnas del CSV:

    modulo, operacion, subtema, tema_soporte, ley

Al importar este módulo:
  - Si existe 'catalogo.csv' válido -> se carga desde ahí.
  - Si no existe o está corrupto   -> se usan los valores por defecto.

Usa exportar_plantilla() para generar el CSV inicial a partir de los valores
por defecto y entregárselo al área funcional para que lo mantengan.
"""

import os
import csv
import re

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CATALOGO_CSV = os.path.join(BASE_DIR, "catalogo.csv")

# Tema de soporte y ley por módulo (nivel módulo).
TEMAS_DEFAULT = {1476: 385, 1862: 383, 836: 384}
LEYES_DEFAULT = {836: "LEY 836", 1476: "LEY 1476", 1862: "LEY 1862"}

# Subtema por (módulo, operación normalizada).
SUBTEMAS_DEFAULT = {
    # LEY 1862
    (1862, "SOPORTE GENERAL"): 651,
    (1862, "BORRADO DE DOCUMENTOS"): 650,
    (1862, "BORRAR ETAPAS"): 649,
    (1862, "BORRAR FUNCIONARIO INST"): 648,
    (1862, "BORRAR FUNCIONARIO COMP"): 647,
    (1862, "CAMBIO RADICADO"): 646,
    (1862, "CAMBIO UNIDAD"): 645,
    (1862, "BORRADO INFRACTOR"): 644,
    (1862, "BORRADO COMPLETO"): 643,
    (1862, "NINGUNA DE LAS ANTERIORES"): 640,

    # LEY 836
    (836, "SOPORTE GENERAL"): 670,
    (836, "FALLOS"): 669,
    (836, "CAMBIO UNIDAD"): 666,
    (836, "BORRADO DE DOCUMENTOS"): 665,
    (836, "BORRADO ACTUACIONES"): 664,
    (836, "ANOTACIONES"): 663,
    (836, "BORRADO INFRACTOR"): 662,
    (836, "BORRADO COMPLETO"): 661,
    (836, "DECISIONES"): 668,
    (836, "NOTIFICACIONES"): 667,

    # LEY 1476
    (1476, "NINGUNA DE LAS ANTERIORES"): 641,
    (1476, "BORRADO COMPLETO"): 652,
    (1476, "SOPORTE GENERAL"): 660,
    (1476, "BORRADO INFRACTOR"): 653,
    (1476, "CAMBIO UNIDAD"): 654,
    (1476, "CAMBIO RADICADO"): 655,
    (1476, "EDITAR ACTORES"): 656,
    (1476, "BORRAR ETAPAS"): 658,
    (1476, "BORRADO DOCUMENTOS"): 659,
    (1476, "NINGUNA ANTERIOR Q"): 642,
}


def _normalizar(operacion):
    """Misma normalización que main.normalizar_operacion (mayúsculas, sin tildes)."""
    op = str(operacion).upper()
    op = re.sub(r"\s+", " ", op).strip()
    return (op.replace("Ó", "O").replace("Í", "I").replace("Á", "A")
              .replace("É", "E").replace("Ú", "U"))


def _filas_desde_defaults():
    filas = []
    for (modulo, operacion), subtema in SUBTEMAS_DEFAULT.items():
        filas.append({
            "modulo": modulo,
            "operacion": operacion,
            "subtema": subtema,
            "tema_soporte": TEMAS_DEFAULT.get(modulo, ""),
            "ley": LEYES_DEFAULT.get(modulo, ""),
        })
    return filas


def exportar_plantilla(path=CATALOGO_CSV):
    """Escribe el catálogo por defecto a CSV para que lo mantenga el área funcional."""
    campos = ["modulo", "operacion", "subtema", "tema_soporte", "ley"]
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=campos)
        w.writeheader()
        w.writerows(_filas_desde_defaults())
    return path


def cargar_catalogo(path=CATALOGO_CSV):
    """
    Devuelve (SUBTEMAS, TEMAS, LEYES).

    Carga desde CSV si existe y es válido; si no, usa los valores por defecto.
    """
    if not os.path.exists(path):
        return dict(SUBTEMAS_DEFAULT), dict(TEMAS_DEFAULT), dict(LEYES_DEFAULT)

    subtemas, temas, leyes = {}, {}, {}
    try:
        with open(path, "r", newline="", encoding="utf-8-sig") as f:
            for fila in csv.DictReader(f):
                modulo = int(str(fila["modulo"]).strip())
                operacion = _normalizar(fila["operacion"])
                subtemas[(modulo, operacion)] = int(str(fila["subtema"]).strip())
                tema = str(fila.get("tema_soporte", "")).strip()
                if tema:
                    temas[modulo] = int(tema)
                ley = str(fila.get("ley", "")).strip()
                if ley:
                    leyes[modulo] = ley
        if not subtemas:
            raise ValueError("catalogo.csv sin filas válidas")
    except (KeyError, ValueError, OSError):
        # CSV corrupto: degradar a valores por defecto en vez de romper el pipeline.
        return dict(SUBTEMAS_DEFAULT), dict(TEMAS_DEFAULT), dict(LEYES_DEFAULT)

    return subtemas, temas, leyes


# Catálogo activo (se carga una vez al importar).
SUBTEMAS, TEMAS, LEYES = cargar_catalogo()
