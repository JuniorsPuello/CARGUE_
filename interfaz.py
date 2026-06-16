import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import os
from main import procesar_documento   # 👈 Importa tu pipeline desde main.py

def seleccionar_pdf():
    archivo = filedialog.askopenfilename(
        title="Seleccionar PDF",
        filetypes=[("Archivos PDF", "*.pdf")]
    )
    if archivo:
        entrada_pdf.set(archivo)

def mostrar_dataframe(df, frame, titulo):
    # Limpiar frame antes de mostrar nueva tabla
    for widget in frame.winfo_children():
        widget.destroy()

    tk.Label(frame, text=titulo, font=("Arial", 12, "bold")).pack(pady=5)

    # Crear tabla con Treeview
    tree = ttk.Treeview(frame, columns=list(df.columns), show="headings", height=8)
    tree.pack(fill="both", expand=True)

    # Definir encabezados
    for col in df.columns:
        tree.heading(col, text=col)
        tree.column(col, width=120, anchor="center")

    # Insertar filas
    for _, row in df.iterrows():
        tree.insert("", "end", values=list(row))

def ejecutar_pipeline():
    pdf_path = entrada_pdf.get()
    if not pdf_path:
        messagebox.showwarning("Advertencia", "Debes seleccionar un archivo PDF.")
        return
    
    try:
        df_ticket, df_mensajes = procesar_documento(pdf_path)
        df_ticket.to_excel("tickets.xlsx", index=False)
        df_mensajes.to_excel("ticket_mensajes.xlsx", index=False)
        
        # Mostrar vista previa en la interfaz
        mostrar_dataframe(df_ticket, frame_tickets, "Vista previa TICKETS")
        mostrar_dataframe(df_mensajes, frame_mensajes, "Vista previa MENSAJES")
        
        # Abrir automáticamente en Excel
        os.startfile("tickets.xlsx")
        os.startfile("ticket_mensajes.xlsx")
        
        messagebox.showinfo("Éxito", "Se generaron y abrieron 'tickets.xlsx' y 'ticket_mensajes.xlsx'.")
    except Exception as e:
        messagebox.showerror("Error", f"Ocurrió un problema:\n{e}")

# ==============================
# INTERFAZ TKINTER
# ==============================
ventana = tk.Tk()
ventana.title("Procesador de PDFs con OCR")
ventana.geometry("900x600")

entrada_pdf = tk.StringVar()

# Sección superior: selección de archivo
tk.Label(ventana, text="Selecciona el archivo PDF:").pack(pady=10)
tk.Entry(ventana, textvariable=entrada_pdf, width=60).pack(pady=5)
tk.Button(ventana, text="Buscar PDF", command=seleccionar_pdf).pack(pady=5)
tk.Button(ventana, text="Procesar Documento", command=ejecutar_pipeline).pack(pady=10)

# Marcos para mostrar tablas
frame_tickets = tk.Frame(ventana)
frame_tickets.pack(fill="both", expand=True, padx=10, pady=10)

frame_mensajes = tk.Frame(ventana)
frame_mensajes.pack(fill="both", expand=True, padx=10, pady=10)

ventana.mainloop()
