from fpdf import FPDF

class PDF(FPDF):
    def header(self):
        self.set_font("Arial", "B", 12)
        self.cell(0, 10, "MINISTERIO DE PRUEBA Y REVISIÓN", border=0, ln=1, align="C")
        self.set_font("Arial", "I", 8)
        self.cell(0, 10, "Documento Sintético para UAT - AbastLG v6", border=0, ln=1, align="C")
        self.ln(10)

    def footer(self):
        self.set_y(-15)
        self.set_font("Arial", "I", 8)
        self.cell(0, 10, f"Página {self.page_no()}", 0, 0, "C")

def create_synthetic_pdf(filepath):
    pdf = PDF()
    pdf.add_page()
    pdf.set_font("Arial", size=11)

    pdf.set_font("Arial", "B", 14)
    pdf.cell(0, 10, "ESPECIFICACIONES TÉCNICAS (EETT)", ln=1, align="C")
    pdf.ln(5)

    pdf.set_font("Arial", "B", 11)
    pdf.cell(0, 10, "1. FINALIDAD PÚBLICA", ln=1)
    pdf.set_font("Arial", "", 11)
    pdf.multi_cell(0, 8, "Adquisición de bienes informáticos y suministros para la operatividad de las oficinas.")
    pdf.ln(5)

    pdf.set_font("Arial", "B", 11)
    pdf.cell(0, 10, "2. ANTECEDENTES Y JUSTIFICACIÓN", ln=1)
    pdf.set_font("Arial", "", 11)
    pdf.multi_cell(0, 8, "Las impresoras actuales requieren suministros urgentes para evitar retrasos en los trámites documentarios.")
    pdf.ln(5)

    pdf.set_font("Arial", "B", 11)
    pdf.cell(0, 10, "3. CARACTERÍSTICAS TÉCNICAS DE LOS BIENES", ln=1)
    pdf.ln(2)

    # Tabla de bienes
    pdf.set_font("Arial", "B", 10)
    col_widths = [15, 30, 80, 60]
    
    # Headers
    pdf.cell(col_widths[0], 10, "ITEM", border=1, align="C")
    pdf.cell(col_widths[1], 10, "CANTIDAD", border=1, align="C")
    pdf.cell(col_widths[2], 10, "DESCRIPCIÓN", border=1, align="C")
    pdf.cell(col_widths[3], 10, "UNIDAD MEDIDA", border=1, align="C")
    pdf.ln(10)

    pdf.set_font("Arial", "", 10)
    
    # Item 1
    # We use multi_cell for description and simulate a row
    x = pdf.get_x()
    y = pdf.get_y()
    
    pdf.rect(x, y, col_widths[0], 20)
    pdf.set_xy(x, y)
    pdf.cell(col_widths[0], 20, "1", align="C")
    
    pdf.rect(x + col_widths[0], y, col_widths[1], 20)
    pdf.set_xy(x + col_widths[0], y)
    pdf.cell(col_widths[1], 20, "3", align="C")
    
    pdf.rect(x + col_widths[0] + col_widths[1], y, col_widths[2], 20)
    pdf.set_xy(x + col_widths[0] + col_widths[1], y)
    desc1 = "Tinta original para EPSON L14150\nCOD. REF. 504 - NEGRO\nCONTENIDO 65-130 mL aprox.\nTIPO FRASCO"
    pdf.multi_cell(col_widths[2], 5, desc1)
    
    pdf.rect(x + col_widths[0] + col_widths[1] + col_widths[2], y, col_widths[3], 20)
    pdf.set_xy(x + col_widths[0] + col_widths[1] + col_widths[2], y)
    pdf.cell(col_widths[3], 20, "UNIDAD", align="C")
    
    pdf.set_y(y + 20)
    
    # Item 2
    x = pdf.get_x()
    y = pdf.get_y()
    
    pdf.rect(x, y, col_widths[0], 25)
    pdf.set_xy(x, y)
    pdf.cell(col_widths[0], 25, "2", align="C")
    
    pdf.rect(x + col_widths[0], y, col_widths[1], 25)
    pdf.set_xy(x + col_widths[0], y)
    pdf.cell(col_widths[1], 25, "2", align="C")
    
    pdf.rect(x + col_widths[0] + col_widths[1], y, col_widths[2], 25)
    pdf.set_xy(x + col_widths[0] + col_widths[1], y)
    desc2 = "Tinta original para EPSON L14150\nCOD. REF. 504 - CIAN\nCONTENIDO 65-130 mL aprox.\nTIPO FRASCO\nESTABILIDAD QUÍMICA 100%"
    pdf.multi_cell(col_widths[2], 5, desc2)
    
    pdf.rect(x + col_widths[0] + col_widths[1] + col_widths[2], y, col_widths[3], 25)
    pdf.set_xy(x + col_widths[0] + col_widths[1] + col_widths[2], y)
    pdf.cell(col_widths[3], 25, "UNIDAD", align="C")
    
    pdf.set_y(y + 25)
    pdf.ln(10)

    pdf.set_font("Arial", "B", 11)
    pdf.cell(0, 10, "4. REQUISITOS DEL PROVEEDOR", ln=1)
    pdf.set_font("Arial", "", 11)
    pdf.multi_cell(0, 8, "- Contar con RUC activo y habido.\n- Contar con RNP vigente en el capitulo de bienes.\n- Contar con Codigo de Cuenta Interbancaria (CCI) registrado.\n- No tener impedimento para contratar con el Estado.\n- No contar con sancion vigente.")
    pdf.ln(5)
    
    pdf.set_font("Arial", "B", 11)
    pdf.cell(0, 10, "5. PLAZO DE ENTREGA", ln=1)
    pdf.set_font("Arial", "", 11)
    pdf.multi_cell(0, 8, "El contratista debera entregar los bienes en un plazo maximo de tres (03) dias calendario posteriores a la notificacion de la orden de compra.")
    pdf.ln(10)

    pdf.set_font("Arial", "I", 14)
    pdf.set_text_color(200, 200, 200)
    pdf.text(120, 250, "SELLO DE RECEPCION: V B")
    pdf.text(120, 260, "FECHA: ___/___/______")
    
    pdf.output(filepath)
    print(f"PDF generado: {filepath}")

if __name__ == "__main__":
    create_synthetic_pdf("/app/tests/e2e/golden_test_uat.pdf")
