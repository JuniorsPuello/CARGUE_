# Actualizaciones del proyecto — Procesador de Oficios (CARGUE_)

**Fecha:** 16 de junio de 2026
**Objetivo:** robustecer el OCR, limpiar el código, modernizar la interfaz y
documentar las decisiones técnicas (incluida la evaluación de un LLM local).

---

## 1. Resumen ejecutivo

| Área | Antes | Después |
|------|-------|---------|
| Captura de IDs (OCR) | **51 / 97 (53%)** | **95 / 97 (98%)** |
| Dependencias externas | Tesseract **+ Poppler** | **Solo Tesseract** |
| Mapeo operación→subtema | Diccionario rígido (fallos silenciosos) | Coincidencia **exacta + difusa** + avisos |
| Catálogo de mapeos | Hardcodeado en el código | **Archivo `catalogo.csv` editable** |
| Validación | Ninguna | **Advertencias** + log de auditoría |
| Pruebas | Ninguna | **13 tests** automáticos |
| Interfaz | Tkinter plano, exporta automático | **CustomTkinter** + **revisión humana** previa |

---

## 2. OCR robustecido (`main.py`)

El documento de prueba es un **PDF escaneado** (imágenes, sin capa de texto), por
lo que el OCR es imprescindible. Mejoras aplicadas, basadas en experimentos
medidos sobre el documento real:

- **Renderizado con `pypdfium2`** en lugar de `pdf2image` → **se elimina la
  dependencia de Poppler**. Solo hace falta instalar Tesseract.
- **Preprocesado de imagen:** escala de grises + **binarización con umbral 120**.
  Un umbral bajo conserva los números tenues de las tablas escaneadas (clave del
  salto de 53% a 98%).
- **Modo de segmentación `--psm 11`** (texto disperso): captura mucho mejor las
  filas de las tablas de números que el modo de bloque uniforme.
- **DPI 300** y motor LSTM (`--oem 1`).
- **Regex tolerantes a errores de OCR:**
  - Radicado: acepta `N°`, `Nº`, `N*`, `No`, `N.`, `Radicad0`, etc.
  - Fecha: tolera acentos/comas/puntos en `Bogotá D.C` + respaldo genérico
    `dd de mes de aaaa`.
  - Tablas: tolera `MODULO/MÓDULO/M0DULO`, `TOTAL: n`, `REGISTR0S`.
  - IDs: ignora marcadores de página para no colar números falsos.

> **Nota de calidad:** en escaneos densos el OCR nunca es 100%. Por eso existe el
> sistema de advertencias y la revisión humana (ver §6 y §8).

---

## 3. Mapeo inteligente operación→subtema (`main.py`)

- **Coincidencia difusa** con `difflib` (librería estándar, sin dependencias ni
  nube → apto para datos clasificados).
- Corrige errores reales: `Borrado Documentos` ahora mapea a **650** (antes caía
  al genérico `641`); tolera ruido de OCR (`BORRADO COMPLET0` → `643`).
- Las operaciones **no reconocidas** se marcan como **advertencia visible** en
  lugar de asignarse en silencio al subtema genérico.

---

## 4. Catálogo externo editable (`catalogo.py` + `catalogo.csv`)

- Los mapeos (módulo → tema, operación → subtema, ley) ya **no están en el
  código**: viven en **`catalogo.csv`**, editable con Excel.
- Columnas: `modulo, operacion, subtema, tema_soporte, ley`.
- Si el CSV falta o está corrupto → se usan los valores por defecto embebidos
  (la aplicación nunca se rompe).
- El área funcional puede ampliar el catálogo **sin tocar código**.

---

## 5. Configuración de rutas (`config.py`)

- **Autodetección de Tesseract** (PATH → rutas de instalación comunes).
- Persistencia de la ruta elegida en **`config.json`** (por máquina).
- La ruta también se puede fijar desde la propia interfaz.

---

## 6. Auditoría y pruebas (`main.py`, `test_main.py`)

- **Logging** a `cargue.log` + consola: registra qué documento se procesó,
  radicado, fecha, IDs por tabla y advertencias → pista de auditoría.
- **13 tests** automáticos (`unittest`, sin dependencias) que cubren
  normalización, extracción de metadatos/tablas, clasificación
  exacta/difusa/desconocida, generación de DataFrame y advertencias.
  - Ejecutar: `py -3.14 -m unittest -v`

---

## 7. Interfaz modernizada (`interfaz.py`)

Evolución del front durante el proyecto, hasta el diseño final:

1. **Revisión humana (flujo seguro):** la app **ya no exporta automáticamente**.
   Flujo: **① Procesar → revisar → ② Generar Excel**.
   - **Tablas editables** (doble clic en cualquier celda; se guarda en los datos
     y se refleja en el Excel).
   - **Filas resaltadas** cuando la operación no se reconoció.
   - **Registro de actividad** con advertencias en vivo.
   - Proceso en **hilo aparte** (no congela la ventana) con **barra de progreso**.
2. **Estilo visual:** rediseño con **CustomTkinter** — fondo oscuro, paneles con
   **bordes cian redondeados**, botones estilizados, fuente monoespaciada
   (Consolas) y pestañas Tickets/Mensajes.

> **Límites de Tkinter:** no reproduce efectos raster (glow/resplandor neón,
> sombras, animaciones de fondo). Para fidelidad visual total a un mockup, la
> alternativa sería un front **web** (HTML/CSS) reutilizando el backend Python.

---

## 8. LLM local — evaluado y descartado (con evidencia)

A petición de probar un modelo de lenguaje local, se instaló y configuró:

- **Ollama** + modelo de visión **minicpm-v** (y prueba con **gemma3:12b**),
  100% local (sin enviar datos a la nube → compatible con datos clasificados).

**Resultado:** los modelos de visión **alucinan los números** de las tablas
densas. Ejemplo (tabla *Borrado Completo*, 28 IDs reales):

| Motor | Resultado |
|-------|-----------|
| **Tesseract** (afinado) | **28/28 correctos** |
| minicpm-v | 2 IDs, totales inventados |
| gemma3:12b | secuencia falsa `38635, 38636 … 38659` |

**Decisión:** **NO** integrar el LLM en la extracción de IDs (inyectaría datos
falsos en un sistema de registro). El código del LLM se **eliminó** del proyecto
y se liberó el modelo descargado. Tesseract afinado + revisión humana es la
combinación correcta y segura.

> Conclusión: para este caso, el valor estuvo en **OCR afinado + fuzzy matching +
> revisión humana**, no en LLM ni en bases vectoriales (pgvector), que serían
> sobre-ingeniería para una taxonomía fija de ~30 subtemas.

---

## 9. Higiene del repositorio

- **`.gitignore`** añadido (ignora `__pycache__/`, `*.xlsx` generados,
  `config.json`, `cargue.log`, `.idea/`).
- Se retiraron del control de versiones los archivos generados que estaban
  versionados (`tickets.xlsx`, `ticket_mensajes.xlsx`, `.pyc`).

---

## 10. Estructura final del proyecto

```
CARGUE_/
├── main.py            # Pipeline: OCR → parseo → mapeo → DataFrames + logging
├── config.py          # Rutas de Tesseract (autodetección + config.json)
├── catalogo.py        # Carga del catálogo (CSV con respaldo embebido)
├── catalogo.csv       # Catálogo de mapeos EDITABLE (Excel)
├── interfaz.py        # GUI CustomTkinter con revisión humana
├── test_main.py       # 13 tests de regresión
├── requirements.txt   # Dependencias
├── ACTUALIZACIONES.md # Este documento
├── cargue.log         # Log de auditoría (generado)
└── prueba.pdf         # Documento de ejemplo
```

### Dependencias (`requirements.txt`)
`pandas`, `openpyxl`, `oracledb`, `pypdfium2`, `pytesseract`, `Pillow`,
`customtkinter`.

### Requisito externo
**Tesseract-OCR** (con idioma español `spa`). Instalado en este equipo en:
`C:\Users\1122125169\AppData\Local\Programs\Tesseract-OCR\tesseract.exe`
(ruta guardada en `config.json`).

---

## 11. Cómo usar

1. Instalar dependencias: `py -3.14 -m pip install -r requirements.txt`
2. Tener Tesseract-OCR instalado (con `spa`).
3. Ejecutar la interfaz: `py -3.14 interfaz.py`
4. Seleccionar PDF → **① Procesar** → revisar/corregir en la tabla →
   **② Generar Excel**.

---

## 12. Pendiente (hoja de ruta)

- **Carga a Oracle** (el paquete `oracledb` aún no se usa): insertar los tickets
  con **dedup/idempotencia** para no duplicar IDs al reprocesar.
- (Opcional) Fondo visual / ajustes finos de la interfaz.
- (Opcional) Front web si se requiere fidelidad de diseño con efectos visuales.
