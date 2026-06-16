from pdf2image import convert_from_path
import pytesseract
import subprocess
import os
import re
import pandas as pd
from datetime import datetime, timedelta


# ==========================================================
# CONFIGURACION TESSERACT
# ==========================================================

def configurar_tesseract():
    langs = subprocess.run(
        ["tesseract", "--list-langs"],
        capture_output=True,
        text=True
    )
    idiomas = langs.stdout.splitlines()
    idioma = "spa" if "spa" in idiomas else "eng"

    tessdata_best_path = r"C:\Program Files\Tesseract-OCR\tessdata_best"
    tessdata_standard_path = r"C:\Program Files\Tesseract-OCR\tessdata"

    if os.path.exists(tessdata_best_path):
        os.environ["TESSDATA_PREFIX"] = tessdata_best_path
    else:
        os.environ["TESSDATA_PREFIX"] = tessdata_standard_path

    return idioma


# ==========================================================
# OCR DEL PDF
# ==========================================================

def extraer_texto_pdf(pdf_path, idioma):
    imagenes = convert_from_path(pdf_path)
    texto_total = ""
    for i, img in enumerate(imagenes):
        texto = pytesseract.image_to_string(img, lang=idioma)
        texto_total += f"\n--- PAGINA {i+1} ---\n{texto}\n"
    return texto_total


# ==========================================================
# LIMPIEZA DE TEXTO OCR
# ==========================================================

def limpiar_texto(texto):
    texto = texto.replace("—", "-").replace("–", "-")
    texto = re.sub(r'(\d{3,6})\s+(\d{3,6})', r'\1 | \2', texto)
    texto = texto.replace("||", "|")
    texto = texto.replace("SOLICITUD", "\nSOLICITUD")
    texto = texto.replace("TOTAL", "\nTOTAL")
    return texto


# ==========================================================
# EXTRAER METADATOS
# ==========================================================

def extraer_metadata(texto):
    
    radicado = None
    fecha = None
    r = re.search(r'Radicado\s*N\*?\s*([A-Za-z0-9/\-\.]+)', texto)
    if r:
        radicado = r.group(1)
    f = re.search(r'Bogotá\s*D\.C[,]*\s*(\d{1,2}\s+de\s+\w+\s+de\s+\d{4})', texto)
    if f:
        fecha = f.group(1).upper()
    return radicado, fecha


# ==========================================================
# EXTRAER TABLAS
# ==========================================================

def extraer_tablas(texto):
    
    tablas = []
    patron = re.compile(
        r'SOLICITUD\s+M[ÓO]DULO\s+(\d+)\s+(.*?)\n(.*?)TOTAL\s+(\d+)\s+REGISTROS',
        re.DOTALL | re.IGNORECASE
    )
    coincidencias = patron.findall(texto)
    for modulo, operacion, contenido, total in coincidencias:
        numeros = re.findall(r'\d{3,6}', contenido)
        ids = [int(n) for n in numeros]
        tablas.append({
            "modulo": int(modulo),
            "operacion": operacion.strip(),
            "ids": ids,
            "total": int(total)
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
    mapa = {1476: 385, 1862: 383, 836: 384}
    return mapa.get(modulo, None)

def obtener_subtema(modulo, operacion):
    operacion = normalizar_operacion(operacion)
    mapa = {
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
    return mapa.get((modulo, operacion), 641)  # fallback genérico


def obtener_ley(modulo):
    mapa = {836: "LEY 836", 1476: "LEY 1476", 1862: "LEY 1862"}
    return mapa.get(modulo, "")

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
        
        # 🔹 Eliminación flexible: busca el patrón ignorando posibles variaciones en guiones o espacios
        # El flag re.IGNORECASE ayuda si el OCR leyó alguna letra en minúscula
        detalle = re.sub(r'/MDN[\s-]COGFM[\s-]COEJC[\s-]DADAE[\s-]29\.54', '', detalle, flags=re.IGNORECASE)
        
        # 🔹 Eliminación corregida: busca el / seguido de todo el código específico
# La parte '/MDN-COGFM-COEJC-DADAE' se borrará
        detalle = re.sub(r'/MDN-COGFM-COEJC-DADAE.*', '', detalle)
        # Eliminamos espacios dobles que hayan quedado tras la limpieza
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
# PIPELINE PRINCIPAL
# ==========================================================

def procesar_documento(pdf_path):
    idioma = configurar_tesseract()
    texto = extraer_texto_pdf(pdf_path, idioma)
    texto = limpiar_texto(texto)
    radicado, fecha = extraer_metadata(texto)
    tablas = extraer_tablas(texto)
    df_ticket = generar_dataframe(tablas)
    df_mensajes = generar_dataframe_mensajes(df_ticket, tablas, radicado, fecha)
    return df_ticket, df_mensajes


# ==========================================================
# EJECUCION
# ==========================================================

if __name__ == "__main__":
    pdf = "prueba.pdf"
    df_ticket, df_mensajes = procesar_documento(pdf)

    print("\n=== TICKETS ===")
    print(df_ticket)

    print("\n=== MENSAJES ===")
    print(df_mensajes)

    # Exportar a Excel
    df_ticket.to_excel("tickets.xlsx", index=False)
    df_mensajes.to_excel("ticket_mensajes.xlsx", index=False)

    print("\nArchivos 'tickets.xlsx' y 'ticket_mensajes.xlsx' generados correctamente.")
