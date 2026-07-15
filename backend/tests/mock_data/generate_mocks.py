import os
from fpdf import FPDF
from PIL import Image, ImageDraw, ImageFont

MOCK_DIR = os.path.dirname(os.path.abspath(__file__))

def create_digital_pdf(filename, content_lines):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", size=12)
    for line in content_lines:
        pdf.cell(200, 10, txt=line, ln=True, align='L')
    pdf.output(os.path.join(MOCK_DIR, filename))

def create_scanned_pdf(filename, content_lines):
    # Generar una imagen con texto
    img = Image.new('RGB', (800, 1000), color=(255, 255, 255))
    d = ImageDraw.Draw(img)
    y_text = 40
    for line in content_lines:
        d.text((40, y_text), line, fill=(0, 0, 0))
        y_text += 20
    
    img_path = os.path.join(MOCK_DIR, "temp_scan.png")
    img.save(img_path)
    
    # Agregar un poco de ruido para simular escaneo si se desea, pero con esto basta
    pdf = FPDF()
    pdf.add_page()
    pdf.image(img_path, 0, 0, 210, 297)
    pdf.output(os.path.join(MOCK_DIR, filename))
    os.remove(img_path)

if __name__ == "__main__":
    req_bienes = [
        "REQUERIMIENTO DE BIENES",
        "I. FINALIDAD PÚBLICA",
        "Adquirir computadoras para la oficina.",
        "II. ANTECEDENTES",
        "La oficina necesita renovar equipos.",
        "III. OBJETIVO DE LA CONTRATACIÓN",
        "Renovar 10 computadoras de escritorio.",
        "X. FORMA DE PAGO",
        "Pago único a la entrega."
    ]
    
    req_scanned_bienes = [
        "REQUERIMIENTO DE COMPRA",
        "l. FlNALlDAD PUBLlCA", # Errores OCR simulados
        "Comprar papel.",
        "ll. ANTECEDENTES",
        "No hay papel.",
        "X. F0RMA DE PAG0",
        "Pago a los 30 dias."
    ]
    
    cotizacion_digital = [
        "COTIZACIÓN N° 001-2024",
        "RUC: 20123456789",
        "Razón Social: TECNOLOGIA SAC",
        "Contacto: ventas@tecnologia.com",
        "Descripción: Computadoras Core i7",
        "Precio Unitario: 3000.00",
        "Cantidad: 10",
        "Total: 30000.00",
        "Condición de pago: Contado a los 15 días",
        "Tiempo de entrega: 7 días calendario",
        "Garantía: 24 meses"
    ]

    create_digital_pdf("req_bienes_digital.pdf", req_bienes)
    create_scanned_pdf("req_bienes_scanned.pdf", req_scanned_bienes)
    create_digital_pdf("cotizacion_digital.pdf", cotizacion_digital)
    print("Mock PDFs generated successfully.")
