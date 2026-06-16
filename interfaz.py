import os
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import customtkinter as ctk

import config
from main import procesar_documento, SUBTEMA_FALLBACK   # 👈 pipeline desde main.py


# ==========================================================
# ESTILO  ·  cyber UI (CustomTkinter, bordes cian)
# ==========================================================
CYAN     = "#2de2ff"
CYAN_DIM = "#1d6b7a"
RED      = "#ff2b3d"
BG       = "#070b12"
PANEL    = "#0a1019"
ENTRY_BG = "#0c1420"
HOVER    = "#10222e"
TXT_DIM  = "#5f8694"

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("dark-blue")

# Estado actual de la revisión (los DataFrames se editan en vivo desde la tabla).
_df_ticket = None
_df_mensajes = None


# ==============================
# HELPERS DE ESTILO
# ==============================

def boton(master, text, command, color=CYAN, fill=False, width=140):
    return ctk.CTkButton(
        master, text=text, command=command, width=width, height=40,
        font=F_BTN, corner_radius=8, border_width=2, border_color=color,
        text_color=("#04232b" if fill else color),
        fg_color=(color if fill else "transparent"),
        hover_color=(color if fill else HOVER),
    )


def panel(master, **kw):
    return ctk.CTkFrame(master, fg_color=PANEL, border_color=CYAN,
                        border_width=2, corner_radius=14, **kw)


# ==============================
# TABLA EDITABLE
# ==============================

def crear_tabla_editable(frame, df, col_resaltar=None, valor_alerta=None):
    """Treeview editable (doble clic). Las ediciones se guardan en el DataFrame."""
    for widget in frame.winfo_children():
        widget.destroy()

    if df is None or df.empty:
        ctk.CTkLabel(frame, text=">> procesa un documento para ver los datos <<",
                     text_color=TXT_DIM, font=F_MONO).pack(pady=40, fill="both", expand=True)
        return

    contenedor = tk.Frame(frame, bg=PANEL)
    contenedor.pack(fill="both", expand=True, padx=6, pady=6)

    columnas = list(df.columns)
    tree = ttk.Treeview(contenedor, columns=columnas, show="headings",
                        height=10, style="Cyber.Treeview")

    scroll_y = ttk.Scrollbar(contenedor, orient="vertical", command=tree.yview)
    scroll_x = ttk.Scrollbar(contenedor, orient="horizontal", command=tree.xview)
    tree.configure(yscrollcommand=scroll_y.set, xscrollcommand=scroll_x.set)
    scroll_y.pack(side="right", fill="y")
    scroll_x.pack(side="bottom", fill="x")
    tree.pack(side="left", fill="both", expand=True)

    tree.tag_configure("par",    background="#0c1420", foreground="#bfe9f5")
    tree.tag_configure("impar",  background="#0f1b29", foreground="#bfe9f5")
    tree.tag_configure("alerta", background="#2a0c1c", foreground="#ff6ec7")

    for col in columnas:
        tree.heading(col, text=col.upper())
        tree.column(col, width=115, anchor="center", stretch=False)

    for n, (idx, row) in enumerate(df.iterrows()):
        if col_resaltar is not None and str(row.get(col_resaltar)) == str(valor_alerta):
            tags = ("alerta",)
        else:
            tags = ("impar",) if n % 2 else ("par",)
        tree.insert("", "end", iid=str(idx), values=list(row), tags=tags)

    _habilitar_edicion(tree, df, columnas)


def _habilitar_edicion(tree, df, columnas):
    """Edición inline: doble clic en una celda abre un Entry y guarda al confirmar."""
    def on_double_click(event):
        if tree.identify_region(event.x, event.y) != "cell":
            return
        rowid = tree.identify_row(event.y)
        colid = tree.identify_column(event.x)
        if not rowid or not colid:
            return
        nombre_col = columnas[int(colid[1:]) - 1]
        celda = tree.bbox(rowid, colid)
        if not celda:
            return
        x, y, w, h = celda

        editor = tk.Entry(tree, bg=ENTRY_BG, fg=CYAN, insertbackground=CYAN,
                          relief="flat", font=("Consolas", 10), justify="center")
        editor.place(x=x, y=y, width=w, height=h)
        editor.insert(0, tree.set(rowid, nombre_col))
        editor.focus_set()
        editor.select_range(0, "end")

        def guardar(_=None):
            nuevo = editor.get()
            tree.set(rowid, nombre_col, nuevo)
            df.at[int(rowid), nombre_col] = nuevo
            editor.destroy()

        editor.bind("<Return>", guardar)
        editor.bind("<FocusOut>", guardar)
        editor.bind("<Escape>", lambda e: editor.destroy())

    tree.bind("<Double-1>", on_double_click)


def log(mensaje, color=CYAN):
    panel_log.configure(state="normal")
    panel_log.insert("end", mensaje + "\n")
    panel_log.see("end")
    panel_log.configure(state="disabled")


def mostrar_advertencias(advertencias):
    if advertencias:
        log("⚠  ALERTA // revisar antes de generar:")
        for a in advertencias:
            log(f"   ▸  {a}")
    else:
        log("✓  sistema ok // sin anomalías detectadas")


# ==============================
# SELECCIÓN DE RUTAS
# ==============================

def seleccionar_pdf():
    archivo = filedialog.askopenfilename(title="Seleccionar PDF",
                                         filetypes=[("Archivos PDF", "*.pdf")])
    if archivo:
        entrada_pdf.delete(0, "end")
        entrada_pdf.insert(0, archivo)


def seleccionar_tesseract():
    archivo = filedialog.askopenfilename(title="Seleccionar tesseract.exe",
                                         filetypes=[("Ejecutable", "tesseract.exe"), ("Todos", "*.*")])
    if archivo:
        entrada_tess.delete(0, "end")
        entrada_tess.insert(0, archivo)


def guardar_configuracion():
    try:
        config.guardar_config({"tesseract_cmd": entrada_tess.get().strip()})
        log(">> configuración guardada")
        messagebox.showinfo("Configuración", "Rutas guardadas correctamente.")
    except Exception as e:
        messagebox.showerror("Error", f"No se pudo guardar la configuración:\n{e}")


# ==============================
# PIPELINE (EN SEGUNDO PLANO)
# ==============================

def ejecutar_pipeline():
    pdf_path = entrada_pdf.get().strip()
    if not pdf_path:
        messagebox.showwarning("Advertencia", "Debes seleccionar un archivo PDF.")
        return
    if not os.path.isfile(pdf_path):
        messagebox.showerror("Error", "El archivo PDF seleccionado no existe.")
        return

    btn_procesar.configure(state="disabled")
    btn_generar.configure(state="disabled")
    barra.set(0)
    log(">> iniciando de-fragmentación (OCR)...")

    tesseract_cmd = entrada_tess.get().strip() or None
    threading.Thread(target=_worker, args=(pdf_path, tesseract_cmd), daemon=True).start()


def _worker(pdf_path, tesseract_cmd):
    """Se ejecuta en un hilo aparte para no congelar la interfaz."""
    try:
        def progreso(pagina, total):
            ventana.after(0, _actualizar_progreso, pagina, total)

        df_ticket, df_mensajes, advertencias = procesar_documento(
            pdf_path, tesseract_cmd=tesseract_cmd, progreso=progreso,
        )
        ventana.after(0, _finalizar_ok, df_ticket, df_mensajes, advertencias)
    except Exception as e:
        ventana.after(0, _finalizar_error, e)


def _actualizar_progreso(pagina, total):
    barra.set(pagina / total if total else 0)
    estado.configure(text=f">> escaneando página {pagina} / {total} ...")


def _finalizar_ok(df_ticket, df_mensajes, advertencias):
    global _df_ticket, _df_mensajes
    _df_ticket, _df_mensajes = df_ticket, df_mensajes

    crear_tabla_editable(tab_tickets, df_ticket,
                         col_resaltar="SUBTEMA_FK", valor_alerta=SUBTEMA_FALLBACK)
    crear_tabla_editable(tab_mensajes, df_mensajes)
    tabview.set("TICKETS")

    log(f">> {len(df_ticket)} tickets generados")
    mostrar_advertencias(advertencias)

    btn_procesar.configure(state="normal")
    btn_generar.configure(state="normal")
    estado.configure(text=f">> {len(df_ticket)} tickets // edita (doble clic) y genera excel")


def _finalizar_error(e):
    btn_procesar.configure(state="normal")
    barra.set(0)
    estado.configure(text=">> error en el proceso")
    log(f"✗  ERROR: {e}")
    messagebox.showerror("Error", f"Ocurrió un problema:\n{e}")


# ==============================
# EXPORTACIÓN (tras la revisión)
# ==============================

def generar_excel():
    if _df_ticket is None or _df_ticket.empty:
        messagebox.showwarning("Sin datos", "Primero procesa un documento.")
        return

    estado.configure(text=">> generando archivos excel...")
    try:
        _df_ticket.to_excel("tickets.xlsx", index=False)
        _df_mensajes.to_excel("ticket_mensajes.xlsx", index=False)
    except PermissionError:
        estado.configure(text=">> error: excel abierto")
        messagebox.showerror("Error",
            "No se pudieron guardar los Excel.\nCierra 'tickets.xlsx' y "
            "'ticket_mensajes.xlsx' si están abiertos e intenta de nuevo.")
        return
    except Exception as e:
        estado.configure(text=">> error al guardar")
        messagebox.showerror("Error", f"No se pudieron guardar los Excel:\n{e}")
        return

    for archivo in ("tickets.xlsx", "ticket_mensajes.xlsx"):
        try:
            os.startfile(archivo)
        except Exception:
            pass

    estado.configure(text=">> excel generado correctamente ✓")
    log(">> excel generado y abierto ✓")
    messagebox.showinfo("Éxito", "Se generaron y abrieron 'tickets.xlsx' y 'ticket_mensajes.xlsx'.")


# ==============================
# INTERFAZ
# ==============================
ventana = ctk.CTk()
ventana.title("CYBER_OS // PROCESADOR DE OFICIOS")
ventana.geometry("1120x900")
ventana.minsize(960, 760)
ventana.configure(fg_color=BG)

# Fuentes (se crean tras instanciar la ventana).
F_TITULO = ctk.CTkFont(family="Consolas", size=24, weight="bold")
F_SUB    = ctk.CTkFont(family="Consolas", size=12)
F_BTN    = ctk.CTkFont(family="Consolas", size=13, weight="bold")
F_MONO   = ctk.CTkFont(family="Consolas", size=12)
F_LABEL  = ctk.CTkFont(family="Consolas", size=12, weight="bold")

# Estilo del Treeview (dark cian).
_style = ttk.Style()
_style.theme_use("clam")
_style.configure("Cyber.Treeview", background=ENTRY_BG, fieldbackground=ENTRY_BG,
                 foreground="#bfe9f5", rowheight=26, borderwidth=0,
                 font=("Consolas", 10))
_style.configure("Cyber.Treeview.Heading", background="#0a1622", foreground=CYAN,
                 font=("Consolas", 9, "bold"), borderwidth=1, relief="flat")
_style.map("Cyber.Treeview", background=[("selected", "#13384a")],
           foreground=[("selected", CYAN)])

entrada_pdf = None  # se crean abajo (CTkEntry)
entrada_tess = None

# --- Marco exterior con borde cian (la "ventana" cyber) ---
shell = panel(ventana)
shell.pack(fill="both", expand=True, padx=16, pady=16)

# --- Encabezado ---
header = ctk.CTkFrame(shell, fg_color="transparent")
header.pack(fill="x", padx=16, pady=(14, 6))
ctk.CTkLabel(header, text="📄  PROCESADOR DE OFICIOS", text_color=CYAN,
             font=F_TITULO).pack(side="left")
ctk.CTkLabel(header, text="OCR · PDFs escaneados → tickets y mensajes",
             text_color=TXT_DIM, font=F_SUB).pack(side="left", padx=14)

# --- Panel: documento + configuración ---
card_io = panel(shell)
card_io.pack(fill="x", padx=16, pady=8)

f1 = ctk.CTkFrame(card_io, fg_color="transparent")
f1.pack(fill="x", padx=14, pady=(14, 6))
ctk.CTkLabel(f1, text="PDF:", text_color=CYAN, font=F_LABEL, width=70,
             anchor="w").pack(side="left")
entrada_pdf = ctk.CTkEntry(f1, font=F_MONO, border_color=CYAN, fg_color=ENTRY_BG,
                           text_color=CYAN, placeholder_text="Selecciona un archivo PDF...",
                           height=40, corner_radius=8)
entrada_pdf.pack(side="left", fill="x", expand=True, padx=(0, 8))
boton(f1, "BUSCAR PDF", seleccionar_pdf).pack(side="left")

f2 = ctk.CTkFrame(card_io, fg_color="transparent")
f2.pack(fill="x", padx=14, pady=(6, 14))
ctk.CTkLabel(f2, text="TESSERACT:", text_color=CYAN, font=F_LABEL, width=70,
             anchor="w").pack(side="left")
entrada_tess = ctk.CTkEntry(f2, font=F_MONO, border_color=CYAN, fg_color=ENTRY_BG,
                            text_color=CYAN, placeholder_text="ruta a tesseract.exe",
                            height=40, corner_radius=8)
entrada_tess.pack(side="left", fill="x", expand=True, padx=(0, 8))
entrada_tess.insert(0, config.cargar_config().get("tesseract_cmd") or "")
boton(f2, "…", seleccionar_tesseract, width=48).pack(side="left", padx=(0, 8))
boton(f2, "GUARDAR", guardar_configuracion, width=110).pack(side="left")

# --- Panel: acciones + progreso ---
card_run = panel(shell)
card_run.pack(fill="x", padx=16, pady=8)
fa = ctk.CTkFrame(card_run, fg_color="transparent")
fa.pack(fill="x", padx=14, pady=(14, 8))
btn_procesar = boton(fa, "①  PROCESAR DOCUMENTO", ejecutar_pipeline, fill=True, width=240)
btn_procesar.pack(side="left", padx=(0, 10))
btn_generar = boton(fa, "②  GENERAR EXCEL", generar_excel, width=180)
btn_generar.pack(side="left")
btn_generar.configure(state="disabled")

barra = ctk.CTkProgressBar(card_run, progress_color=CYAN, fg_color=ENTRY_BG,
                           height=14, corner_radius=8)
barra.pack(fill="x", padx=14, pady=(2, 4))
barra.set(0)
estado = ctk.CTkLabel(card_run, text=">> sistema listo. esperando datos",
                      text_color=CYAN, font=F_MONO, anchor="w")
estado.pack(fill="x", padx=14, pady=(0, 12))

# --- Panel: tablas (pestañas) ---
tabview = ctk.CTkTabview(shell, fg_color=PANEL, border_color=CYAN, border_width=2,
                         corner_radius=14, segmented_button_selected_color=CYAN,
                         segmented_button_selected_hover_color=CYAN,
                         text_color=CYAN, segmented_button_unselected_color=PANEL)
tabview.pack(fill="both", expand=True, padx=16, pady=8)
tab_tickets = tabview.add("TICKETS")
tab_mensajes = tabview.add("MENSAJES")
ctk.CTkLabel(tab_tickets, text=">> procesa un documento para ver los tickets <<",
             text_color=TXT_DIM, font=F_MONO).pack(pady=40)

# --- Panel: registro de actividad ---
card_log = panel(shell)
card_log.pack(fill="x", padx=16, pady=(8, 16))
ctk.CTkLabel(card_log, text="REGISTRO DE ACTIVIDAD", text_color=CYAN,
             font=F_LABEL).pack(anchor="w", padx=14, pady=(10, 0))
panel_log = ctk.CTkTextbox(card_log, height=120, font=("Consolas", 11),
                           fg_color=ENTRY_BG, text_color=CYAN, border_color=CYAN_DIM,
                           border_width=1, corner_radius=8)
panel_log.pack(fill="x", padx=14, pady=(4, 14))
panel_log.insert("end", ">> el registro de actividad aparecerá aquí...\n")
panel_log.configure(state="disabled")

ventana.mainloop()
