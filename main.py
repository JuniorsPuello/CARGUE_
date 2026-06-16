import pypdfium2 as pdfium
from PIL import ImageOps
import pytesseract
import os
import re
import difflib
import logging
import pandas as pd
from datetime import datetime, timedelta

import config
import catalogo

# ==========================================================
# LOGGING / AUDITORÍA
# ==========================================================
# Registro en archivo (cargue.log) + consola. Sirve de pista de auditoría:
# qué PDF se procesó, cuántas tablas/IDs y qué advertencias salieron.

LOG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cargue.log")

logger = logging.getLogger("cargue")
if not logger.handlers:
    logger.setLevel(logging.INFO)
    _fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
    _fh = logging.FileHandler(LOG_PATH, encoding="utf-8")
    _fh.setFormatter(_fmt)
    logger.addHandler(_fh)
    _ch = logging.StreamHandler()
    _ch.setFormatter(_fmt)
    logger.addHandler(_ch)

# ==========================================================
# CONFIGURACION TESSERACT
# ==========================================================

def configurar_tesseract(tesseract_cmd=None):
    """Configura la ruta de Tesseract y el TESSDATA_PREFIX. Devuelve el idioma a usar."""
    if tesseract_cmd:
        pytesseract.pytesseract.tesseract_cmd = tesseract_cmd
        base = os.path.dirname(tesseract_cmd)
        tessdata_best = os.path.join(base, "tessdata_best")
        tessdata_std = os.path.join(base, "tessdata")
        if os.path.exists(tessdata_best):
            os.environ["TESSDATA_PREFIX"] = tessdata_best
        elif os.path.exists(tessdata_std):
            os.environ["TESSDATA_PREFIX"] = tessdata_std

    # Detectar idioma disponible sin recurrir a subprocess.
    try:
        idiomas = pytesseract.get_languages(config="")
    except Exception:
        idiomas = []
    return "spa" if "spa" in idiomas else "eng"


# ==========================================================
# OCR DEL PDF
# ==========================================================

# Umbral de binarización: valores bajos conservan números tenues de las tablas
# escaneadas. 120 dio la mejor captura empírica (95/97 IDs) en documentos reales.
UMBRAL_BINARIZACION = 120


def _preprocesar_imagen(img):
    """
    Escala de grises + binarización.

    La binarización (blanco/negro puro) resulta clave para que el OCR lea las
    tablas densas de números de los oficios escaneados; el autocontraste solo
    no basta.
    """
    gris = ImageOps.grayscale(img)
    return gris.point(lambda x: 0 if x < UMBRAL_BINARIZACION else 255, mode="1")


def extraer_texto_pdf(pdf_path, idioma, dpi=300, progreso=None):
    """
    Renderiza el PDF a imágenes (con pypdfium2, sin Poppler) y aplica OCR página
    por página.

    progreso: callback opcional progreso(pagina_actual, total_paginas) para la GUI.
    """
    pdf = pdfium.PdfDocument(pdf_path)
    total = len(pdf)
    escala = dpi / 72.0  # pypdfium2 trabaja en puntos (72 = 100%).

    # --oem 1: motor LSTM (más preciso).
    # --psm 11: "texto disperso"; captura mucho mejor las filas de las tablas de
    # números de los oficios escaneados que el modo de bloque uniforme.
    config_ocr = "--oem 1 --psm 11"

    texto_total = ""
    try:
        for i in range(total):
            img = pdf[i].render(scale=escala).to_pil()
            img_proc = _preprocesar_imagen(img)
            texto = pytesseract.image_to_string(img_proc, lang=idioma, config=config_ocr)
            texto_total += f"\n--- PAGINA {i + 1} ---\n{texto}\n"
            if progreso:
                progreso(i + 1, total)
    finally:
        pdf.close()

    return texto_total


# ==========================================================
# LIMPIEZA DE TEXTO OCR
# ==========================================================

def limpiar_texto(texto):
    # Normaliza distintos tipos de guion a '-'.
    texto = texto.replace("—", "-").replace("–", "-").replace("‑", "-")
    # Separador visual entre números contiguos (ayuda a la lectura, no a la extracción).
    texto = re.sub(r'(\d{3,6})\s+(\d{3,6})', r'\1 | \2', texto)
    texto = texto.replace("||", "|")
    # Forzar saltos de línea antes de palabras clave para que las regex anclen mejor.
    texto = re.sub(r'\bSOLICITUD\b', '\nSOLICITUD', texto, flags=re.IGNORECASE)
    texto = re.sub(r'\bTOTAL\b', '\nTOTAL', texto, flags=re.IGNORECASE)
    return texto


# ==========================================================
# EXTRAER METADATOS
# ==========================================================

def extraer_metadata(texto):
    """Extrae (radicado, fecha) tolerando variantes típicas del OCR."""
    radicado = None
    fecha = None

    # Radicado: tolera 'N°', 'Nº', 'N*', 'No', 'N.', 'Radicad0', etc.
    r = re.search(
        r'Radicad[o0]\s*(?:N[º°oO\*\.:\s]*)?\s*([A-Za-z0-9/\-\.]+)',
        texto, re.IGNORECASE
    )
    if r:
        radicado = r.group(1).strip(" .-")

    # Fecha tras 'Bogotá D.C': tolera acentos, comas/puntos y espacios variables.
    f = re.search(
        r'Bogot[aá]\s*[,\.]?\s*D\s*[\.,]?\s*C\s*[,\.]?\s*'
        r'(\d{1,2}\s+de\s+[a-zA-ZáéíóúÁÉÍÓÚ]+\s+de\s+\d{4})',
        texto, re.IGNORECASE
    )
    if f:
        fecha = f.group(1).upper()
    else:
        # Respaldo: cualquier patrón "dd de mes de aaaa" en el documento.
        f2 = re.search(
            r'(\d{1,2}\s+de\s+[a-zA-ZáéíóúÁÉÍÓÚ]+\s+de\s+\d{4})',
            texto, re.IGNORECASE
        )
        if f2:
            fecha = f2.group(1).upper()

    return radicado, fecha


# ==========================================================
# EXTRAER TABLAS
# ==========================================================

def _extraer_ids(contenido):
    """Obtiene los IDs (3-6 dígitos) de un bloque, ignorando marcadores de página."""
    contenido = re.sub(r'-{2,}\s*PAGINA\s*\d+\s*-{2,}', ' ', contenido, flags=re.IGNORECASE)
    numeros = re.findall(r'\d{3,6}', contenido)
    return [int(n) for n in numeros]


def extraer_tablas(texto):
    """
    Extrae bloques 'SOLICITUD MÓDULO <n> <operación> ... TOTAL <n> REGISTROS'.

    Tolerante a variantes de OCR: MODULO/MÓDULO/M0DULO, 'TOTAL: n', REGISTR0S, etc.
    """
    tablas = []
    patron = re.compile(
        r'SOLICITUD\s+M[ÓÒO0]DUL[O0]\s+(\d{2,5})\s+(.*?)\n'
        r'(.*?)\bTOTAL\b\s*[:\-]?\s*(\d{1,5})\s+REGISTR[O0]S',
        re.DOTALL | re.IGNORECASE
    )
    for modulo, operacion, contenido, total in patron.findall(texto):
        tablas.append({
            "modulo": int(modulo),
            "operacion": operacion.strip(),
            "ids": _extraer_ids(contenido),
            "total": int(total),
        })
    return tablas


# ==========================================================
# MAPEOS
# ==========================================================

def normalizar_operacion(operacion):
    operacion = operacion.upper()
    operacion = re.sub(r'\s+', ' ', operacion).strip()
    operacion = operacion.replace("Ó", "O").replace("Í", "I").replace("Á", "A").replace("É", "E").replace("Ú", "U")
    return operacion

def obtener_tema_soporte(modulo):
    return catalogo.TEMAS.get(modulo, None)


# Subtema genérico cuando la operación no se reconoce en el catálogo.
SUBTEMA_FALLBACK = 641

# Umbral de similitud (0-1) para aceptar una coincidencia difusa de operación.
# Por debajo, la operación se considera "no reconocida" y se marca como advertencia.
UMBRAL_OPERACION = 0.82


def clasificar_operacion(modulo, operacion):
    """
    Mapea (módulo, operación) a su subtema.

    Devuelve (subtema, reconocida):
      1. Coincidencia exacta en el catálogo.
      2. Coincidencia difusa dentro del mismo módulo (tolera errores de OCR como
         'BORRADO DOCUMENTOS' -> 'BORRADO DE DOCUMENTOS').
      3. Si nada supera UMBRAL_OPERACION: (SUBTEMA_FALLBACK, False) -> no reconocida.
    """
    op = normalizar_operacion(operacion)

    if (modulo, op) in catalogo.SUBTEMAS:
        return catalogo.SUBTEMAS[(modulo, op)], True

    mejor_sub, mejor_score = SUBTEMA_FALLBACK, 0.0
    for (m, nombre), sub in catalogo.SUBTEMAS.items():
        if m != modulo:
            continue
        score = difflib.SequenceMatcher(None, op, nombre).ratio()
        if score > mejor_score:
            mejor_sub, mejor_score = sub, score

    if mejor_score >= UMBRAL_OPERACION:
        return mejor_sub, True
    return SUBTEMA_FALLBACK, False


def obtener_subtema(modulo, operacion):
    return clasificar_operacion(modulo, operacion)[0]


def obtener_ley(modulo):
    return catalogo.LEYES.get(modulo, "")

def normalizar_asunto(asunto):
    asunto = str(asunto).upper()
    asunto = re.sub(r'\s+', ' ', asunto).strip()
    return asunto


# ==========================================================
# DATAFRAME TICKET
# ==========================================================

def generar_dataframe(tablas):
    hoy = datetime.now()
    fecha_crea = hoy.strftime("%d/%m/%y")
    fecha_vence = (hoy + timedelta(days=3)).strftime("%d/%m/%y")
    fecha_eval  = (hoy + timedelta(days=1)).strftime("%d/%m/%y")

    filas = []
    id_seq = 1
    for tabla in tablas:
        modulo = tabla["modulo"]
        operacion = tabla["operacion"]
        tema = obtener_tema_soporte(modulo)
        subtema = obtener_subtema(modulo, operacion)
        for numero in tabla["ids"]:
            fila = {
                "ID": id_seq,
                "CODIGO_TICKET": "BAICC",
                "FECHA_CREA_TICK": fecha_crea,
                "FECHA_VENCE_TICK": fecha_vence,
                "ESTADO_TICKET": 5,
                "ACUERDO_N_S_FK": 6,
                "TEMA_SOPORTE_FK": tema,
                "EMP_CREA_FK": 364,
                "SITIO_TRABAJO": "JEMOP",
                "FECHA_CIERRE": fecha_crea,
                "FECHA_EVALUACION": fecha_eval,
                # 🔹 ASUNTO ahora en mayúsculas
                "ASUNTO": normalizar_asunto(operacion),
                "EMP_TEC_ASIGNADO_FK": 240,
                "EQUIPO_SOP_FK": "",
                "EVAL_SERVICIO_FK": "",
                "UNIDAD_ORIGEN": 100000022176,
                "FUERZA_ORIGE": 3,
                "ACCIONES": "",
                "SUBTEMA_FK": subtema,
                "DEPARTAMENTO": "CAOCC",
                "DIRECCION_DEPENDENCIA": "BAICC",
                "OFICINA": "COMPAÑIA B",
                "TELEFONO_ADICIONAL": numero,
                "FUERZA_TEC_ASIGNADO": 3,
                "UNIDAD_TEC_ASIGNADO": 100000022176,
                "MED_PEDAGOGICA_FK": ""
            }
            filas.append(fila)
            id_seq += 1
    return pd.DataFrame(filas)


# ==========================================================
# DATAFRAME TICKET_MENSAJE
# ==========================================================

def generar_dataframe_mensajes(df_ticket, tablas, radicado, fecha_doc):
    filas = []
    if not radicado:
        radicado = "SIN RADICADO"
    if not fecha_doc:
        fecha_doc = datetime.now().strftime("%d DE %B DE %Y").upper()

    relacion = []
    for tabla in tablas:
        for _ in tabla["ids"]:
            relacion.append(tabla["modulo"])

    for i, (_, row) in enumerate(df_ticket.iterrows()):
        modulo = relacion[i]
        ley = obtener_ley(modulo)
        asunto = normalizar_asunto(row["ASUNTO"])
        detalle = (
            f"REQUERIMIENTO {asunto} {ley} "
            f"DE ACUERDO A RADICADO N* {radicado} "
            f"BOGOTÁ D.C, CON FECHA {fecha_doc}"
        )
        detalle = re.sub(r'\s+', ' ', detalle)

        # Elimina el código interno '/MDN-COGFM-COEJC-DADAE...' tolerando que el OCR
        # haya leído guiones/espacios/subrayados distintos (una sola pasada flexible).
        detalle = re.sub(r'/?\s*MDN[\s\-_]*COGFM[\s\-_]*COEJC[\s\-_]*DADAE.*',
                         '', detalle, flags=re.IGNORECASE)
        detalle = re.sub(r'\s+', ' ', detalle).strip()

        fila = {
            "ID": None,
            "DETALLE_MENSAJE": detalle,
            "FECHA_ENVIO": datetime.now().strftime("%d/%m/%y"),
            "EMPLEADO_ENVIA_FK": row["EMP_CREA_FK"],
            "TIPO_MENSAJE": "M_PUB",
            "TICKET_FK": row["ID"]
        }
        filas.append(fila)

    return pd.DataFrame(filas)


# ==========================================================
# VALIDACION / ADVERTENCIAS
# ==========================================================

def _generar_advertencias(tablas, radicado, fecha):
    """Recopila avisos de calidad de extracción para mostrar al usuario."""
    advertencias = []
    if not tablas:
        advertencias.append(
            "No se detectó ninguna tabla 'SOLICITUD MÓDULO ... TOTAL N REGISTROS'. "
            "Revisa la calidad del escaneo o el formato del documento."
        )
    if not radicado:
        advertencias.append("No se detectó el número de radicado (se usará 'SIN RADICADO').")
    if not fecha:
        advertencias.append("No se detectó la fecha del documento (se usará la fecha de hoy).")
    for t in tablas:
        if t["total"] != len(t["ids"]):
            advertencias.append(
                f"Módulo {t['modulo']} ({t['operacion'] or 's/operación'}): "
                f"el documento indica {t['total']} registros pero se detectaron "
                f"{len(t['ids'])}. Verifica el OCR."
            )
        _, reconocida = clasificar_operacion(t["modulo"], t["operacion"])
        if not reconocida:
            advertencias.append(
                f"Operación no reconocida en el catálogo: módulo {t['modulo']} "
                f"'{t['operacion']}' → se asignó el subtema genérico {SUBTEMA_FALLBACK}. "
                f"Amplía el catálogo (catalogo.csv) o revísala."
            )
    return advertencias


# ==========================================================
# PIPELINE PRINCIPAL
# ==========================================================

def procesar_documento(pdf_path, tesseract_cmd=None, progreso=None):
    """
    Pipeline completo: OCR -> parseo -> DataFrames.

    Devuelve (df_ticket, df_mensajes, advertencias).
    Si no se pasa la ruta de Tesseract, se autodetecta vía config.py.
    """
    cfg = config.cargar_config()
    tesseract_cmd = tesseract_cmd or cfg["tesseract_cmd"]

    logger.info("Procesando documento: %s", pdf_path)
    idioma = configurar_tesseract(tesseract_cmd)
    texto = extraer_texto_pdf(pdf_path, idioma, progreso=progreso)
    texto = limpiar_texto(texto)
    radicado, fecha = extraer_metadata(texto)
    tablas = extraer_tablas(texto)
    logger.info("Radicado=%s | Fecha=%s | tablas=%d", radicado, fecha, len(tablas))
    for t in tablas:
        logger.info("  Módulo %s '%s': %d/%d IDs",
                    t["modulo"], t["operacion"], len(t["ids"]), t["total"])

    df_ticket = generar_dataframe(tablas)
    df_mensajes = generar_dataframe_mensajes(df_ticket, tablas, radicado, fecha)
    advertencias = _generar_advertencias(tablas, radicado, fecha)

    logger.info("Tickets generados: %d | advertencias: %d", len(df_ticket), len(advertencias))
    for a in advertencias:
        logger.warning("ADVERTENCIA: %s", a)
    return df_ticket, df_mensajes, advertencias


# ==========================================================
# EJECUCION
# ==========================================================

if __name__ == "__main__":
    pdf = "prueba.pdf"
    df_ticket, df_mensajes, advertencias = procesar_documento(pdf)

    print("\n=== TICKETS ===")
    print(df_ticket)

    print("\n=== MENSAJES ===")
    print(df_mensajes)

    if advertencias:
        print("\n=== ADVERTENCIAS ===")
        for a in advertencias:
            print(f" - {a}")

    # Exportar a Excel
    df_ticket.to_excel("tickets.xlsx", index=False)
    df_mensajes.to_excel("ticket_mensajes.xlsx", index=False)

    print("\nArchivos 'tickets.xlsx' y 'ticket_mensajes.xlsx' generados correctamente.")
