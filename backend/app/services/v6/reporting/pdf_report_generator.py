import os
import uuid
import hashlib
from decimal import Decimal
import xml.sax.saxutils
from typing import Dict, Any, Tuple, List, Optional
from io import BytesIO

from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, KeepTogether
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from reportlab.pdfgen import canvas
import fitz  # PyMuPDF


class NumberedCanvas(canvas.Canvas):
    """
    Canvas de ReportLab de dos pasadas para calcular el número total de páginas
    e imprimir un pie de página institucional seguro con el hash de integridad del snapshot.
    """
    def __init__(self, *args, **kwargs):
        self.snapshot_hash = kwargs.pop("snapshot_hash", "NO_HASH")
        super().__init__(*args, **kwargs)
        self._saved_page_states = []

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        page_count = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self.draw_footer(page_count)
            super().showPage()
        super().save()

    def draw_footer(self, page_count):
        self.saveState()
        self.setFont("Helvetica", 7)
        self.setFillColorRGB(0.35, 0.35, 0.35)
        
        # Línea separadora
        self.setStrokeColorRGB(0.8, 0.8, 0.8)
        self.setLineWidth(0.5)
        self.line(40, 45, 572, 45)

        # Advertencia legal y hash lógico del snapshot
        legal_text = "La aprobación interna de este informe no constituye otorgamiento de la buena pro, adjudicación ni contrato."
        self.drawString(40, 34, legal_text)
        
        hash_disp = f"Hash Snapshot: {self.snapshot_hash[:32]}... | Pág. {self._pageNumber} de {page_count}"
        self.drawRightString(572, 34, hash_disp)
        
        self.restoreState()


class PdfReportGenerator:
    """
    Generador de informes técnicos en PDF mediante ReportLab real.
    Garantiza:
    - 12 secciones estructurales canónicas acordadas en Issue #14.
    - Escape riguroso de caracteres XML/HTML mediante xml.sax.saxutils.escape en todo Paragraph.
    - Manejo seguro de cadenas largas con wrap automático en tablas ReportLab.
    - Verificación binaria y semántica con PyMuPDF antes de publicación.
    - Almacenamiento seguro atómico mediante fsync, os.replace, realpath y commonpath anti-traversal.
    - Reconciliación de archivos huérfanos para recuperación tras caídas del proceso.
    """

    @classmethod
    def escape_xml(cls, val: Any) -> str:
        if val is None:
            return ""
        return xml.sax.saxutils.escape(str(val))

    @classmethod
    def format_money(cls, val: Any) -> str:
        if val is None or val == "":
            return "0.00"
        try:
            d = Decimal(str(val))
            return f"{d:,.2f}"
        except Exception:
            return str(val)

    @classmethod
    def format_decimal(cls, val: Any, decimals: int = 2) -> str:
        if val is None or val == "":
            return "-"
        try:
            d = Decimal(str(val))
            return f"{d:.{decimals}f}"
        except Exception:
            return str(val)

    @classmethod
    def generate_pdf_bytes(
        cls,
        snapshot: Dict[str, Any],
        approval_meta: Dict[str, Any]
    ) -> Tuple[bytes, str]:
        """
        Construye el documento PDF con las 12 secciones en memoria y calcula su hash SHA-256.
        Retorna (pdf_bytes, pdf_hash).
        """
        buffer = BytesIO()
        doc = SimpleDocTemplate(
            buffer,
            pagesize=letter,
            leftMargin=40,
            rightMargin=40,
            topMargin=40,
            bottomMargin=55
        )

        styles = getSampleStyleSheet()
        title_style = ParagraphStyle(
            'ReportTitle',
            parent=styles['Heading1'],
            fontSize=14,
            leading=17,
            textColor=colors.HexColor('#1E293B'),
            spaceAfter=4
        )
        subtitle_style = ParagraphStyle(
            'ReportSubtitle',
            parent=styles['Normal'],
            fontSize=8,
            leading=11,
            textColor=colors.HexColor('#64748B'),
            spaceAfter=10
        )
        h2_style = ParagraphStyle(
            'SectionH2',
            parent=styles['Heading2'],
            fontSize=10,
            leading=13,
            textColor=colors.HexColor('#0F172A'),
            spaceBefore=8,
            spaceAfter=4
        )
        body_style = ParagraphStyle(
            'Body',
            parent=styles['Normal'],
            fontSize=7.5,
            leading=10,
            textColor=colors.HexColor('#334155')
        )
        bold_style = ParagraphStyle(
            'BodyBold',
            parent=body_style,
            fontName='Helvetica-Bold'
        )
        legal_style = ParagraphStyle(
            'LegalDisclaimer',
            parent=styles['Normal'],
            fontSize=7,
            leading=9,
            textColor=colors.HexColor('#B91C1C'),
            fontName='Helvetica-Bold'
        )

        elements = []

        # Encabezado
        metadata = snapshot.get("metadata", {})
        case_code = cls.escape_xml(metadata.get("case_code", "-"))
        version_num = cls.escape_xml(str(metadata.get("version_number", 1)))

        elements.append(Paragraph("INFORME TÉCNICO DE EVALUACIÓN Y SELECCIÓN INTERNA", title_style))
        elements.append(Paragraph(f"Expediente: {case_code} &nbsp;|&nbsp; Versión N.º: {version_num}", subtitle_style))
        elements.append(Spacer(1, 4))

        # Extracción de datos para las 12 secciones
        winner = snapshot.get("winner", {})
        s1 = snapshot.get("section_1_case_object", {})
        s2 = snapshot.get("section_2_antecedents", {})
        s3 = snapshot.get("section_3_examined_documents", [])
        s4 = snapshot.get("section_4_suppliers_offers", [])
        s5 = snapshot.get("section_5_requirements_matrix", [])
        s6 = snapshot.get("section_6_evidence_traceability", [])
        s7 = snapshot.get("section_7_non_conformities", [])
        s8 = snapshot.get("section_8_improvements", [])
        s9 = snapshot.get("section_9_contractual_conditions", {})
        s10 = snapshot.get("section_10_economic_vfm", [])
        s11 = snapshot.get("section_11_motivation_selection", {})

        table_base_style = TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#F8FAFC')),
            ('INNERGRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#E2E8F0')),
            ('BOX', (0, 0), (-1, -1), 0.5, colors.HexColor('#CBD5E1')),
            ('TOPPADDING', (0, 0), (-1, -1), 3),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
            ('LEFTPADDING', (0, 0), (-1, -1), 4),
            ('RIGHTPADDING', (0, 0), (-1, -1), 4),
        ])

        # 1. Expediente y Objeto de la Contratación
        elements.append(Paragraph("1. Expediente y Objeto de la Contratación", h2_style))
        s1_data = [
            [Paragraph("Código / SIGA:", bold_style), Paragraph(cls.escape_xml(s1.get('case_code', metadata.get('case_code', '-'))), body_style)],
            [Paragraph("Título / Objeto:", bold_style), Paragraph(cls.escape_xml(s1.get('object_title', '-')), body_style)],
            [Paragraph("Tipo de Contratación:", bold_style), Paragraph(cls.escape_xml(s1.get('contract_type', '-')), body_style)],
            [Paragraph("Entidad Convocante:", bold_style), Paragraph(cls.escape_xml(s1.get('entity_name', 'Entidad Convocante')), body_style)],
        ]
        t1 = Table(s1_data, colWidths=[130, 400])
        t1.setStyle(table_base_style)
        elements.append(t1)
        elements.append(Spacer(1, 4))

        # 2. Antecedentes Administrativos
        elements.append(Paragraph("2. Antecedentes Administrativos y Régimen Normativo", h2_style))
        elements.append(Paragraph(
            f"<b>Régimen Normativo Aplicable:</b> {cls.escape_xml(snapshot.get('legal_regime_notice', 'Régimen normativo específico no determinado; requiere validación administrativa.'))}",
            body_style
        ))
        elements.append(Paragraph(
            f"<b>Estado del Flujo:</b> {cls.escape_xml(s2.get('workflow_status', 'APPROVED'))} &nbsp;|&nbsp; <b>Resumen:</b> {cls.escape_xml(s2.get('summary', 'Expediente tramitado y evaluado bajo el flujo institucional.'))}",
            body_style
        ))
        elements.append(Spacer(1, 4))

        # 3. Documentos Examinados y Hashes Sustentados
        elements.append(Paragraph("3. Documentos Examinados y Hashes Sustentados", h2_style))
        if s3:
            s3_data = [[Paragraph("ID", bold_style), Paragraph("Archivo", bold_style), Paragraph("Tipo", bold_style), Paragraph("Checksum / Estado", bold_style)]]
            for d in s3:
                s3_data.append([
                    Paragraph(cls.escape_xml(str(d.get('id', '-'))), body_style),
                    Paragraph(cls.escape_xml(d.get('filename', '-')), body_style),
                    Paragraph(cls.escape_xml(d.get('document_type', '-')), body_style),
                    Paragraph(cls.escape_xml(d.get('sha256', d.get('status', 'REGISTRADO'))), body_style)
                ])
            t3 = Table(s3_data, colWidths=[35, 180, 115, 200])
            t3.setStyle(table_base_style)
            elements.append(t3)
        else:
            elements.append(Paragraph("No se registraron documentos anexos en el expediente.", body_style))
        elements.append(Spacer(1, 4))

        # 4. Proveedores Participantes y Ofertas Presentadas
        elements.append(Paragraph("4. Proveedores Participantes y Ofertas Presentadas", h2_style))
        winner_sup_name = winner.get('supplier_name', '-')
        winner_ruc = winner.get('supplier_ruc', '-')
        winner_curr = winner.get('currency', 'PEN')
        winner_amount = cls.format_money(winner.get('total_amount', 0.0))

        s4_data = [[Paragraph("Proveedor", bold_style), Paragraph("RUC", bold_style), Paragraph("Monto Ofertado", bold_style), Paragraph("Estado", bold_style)]]
        if s4:
            for off in s4:
                s4_data.append([
                    Paragraph(cls.escape_xml(off.get('supplier_name', '-')), body_style),
                    Paragraph(cls.escape_xml(off.get('supplier_ruc', '-')), body_style),
                    Paragraph(f"{cls.escape_xml(off.get('currency', 'PEN'))} {cls.format_money(off.get('total_amount', 0.0))}", body_style),
                    Paragraph(cls.escape_xml(off.get('status', '-')), body_style)
                ])
        else:
            s4_data.append([
                Paragraph(cls.escape_xml(winner_sup_name), body_style),
                Paragraph(cls.escape_xml(winner_ruc), body_style),
                Paragraph(f"{cls.escape_xml(winner_curr)} {winner_amount}", body_style),
                Paragraph("SELECCIONADO", body_style)
            ])
        t4 = Table(s4_data, colWidths=[200, 100, 130, 100])
        t4.setStyle(table_base_style)
        elements.append(t4)
        elements.append(Spacer(1, 4))

        # 5. Matriz de Requisitos y Evaluación Técnica
        elements.append(Paragraph("5. Matriz de Evaluación Técnica y Cumplimiento de Requisitos", h2_style))
        reqs = s5 or snapshot.get("requirements", [])
        if reqs:
            s5_data = [[Paragraph("Requisito", bold_style), Paragraph("Obligatorio", bold_style), Paragraph("Resultado Técnico", bold_style)]]
            for r in reqs:
                mand_str = "Sí" if r.get("mandatory") else "No"
                s5_data.append([
                    Paragraph(cls.escape_xml(r.get("description", "-")), body_style),
                    Paragraph(mand_str, body_style),
                    Paragraph(cls.escape_xml(r.get("evaluation_status", "-")), body_style)
                ])
            t5 = Table(s5_data, colWidths=[330, 90, 110])
            t5.setStyle(table_base_style)
            elements.append(t5)
        else:
            elements.append(Paragraph("No se registraron requerimientos en la matriz técnica.", body_style))
        elements.append(Spacer(1, 4))

        # 6. Trazabilidad de Evidencias Acreditadas
        elements.append(Paragraph("6. Trazabilidad de Evidencias Acreditadas (Página, Fragmento y Verificador)", h2_style))
        evidences = s6 or []
        if evidences:
            s6_data = [[
                Paragraph("Requisito", bold_style),
                Paragraph("Documento Sustento", bold_style),
                Paragraph("Pág.", bold_style),
                Paragraph("Fragmento Textual Acreditado", bold_style),
                Paragraph("Estado", bold_style),
                Paragraph("Verificador", bold_style)
            ]]
            for ev in evidences:
                page_str = str(ev.get('page')) if ev.get('page') is not None else "-"
                frag_str = f"<i>\"{cls.escape_xml(ev.get('fragment'))}\"</i>" if ev.get('fragment') else "-"
                s6_data.append([
                    Paragraph(cls.escape_xml(ev.get('requirement', '-')), body_style),
                    Paragraph(cls.escape_xml(ev.get('document_name', '-')), body_style),
                    Paragraph(cls.escape_xml(page_str), body_style),
                    Paragraph(frag_str, body_style),
                    Paragraph(cls.escape_xml(ev.get('status', 'VERIFICADO')), body_style),
                    Paragraph(cls.escape_xml(ev.get('verified_by', '-')), body_style),
                ])
            t6 = Table(s6_data, colWidths=[120, 100, 30, 160, 55, 65])
            t6.setStyle(table_base_style)
            elements.append(t6)
        else:
            elements.append(Paragraph("No se registraron evidencias documentales trazadas en el expediente.", body_style))
        elements.append(Spacer(1, 4))

        # 7. Resultados No Conformes y Revisión Humana
        elements.append(Paragraph("7. Resultados No Conformes y Revisión Humana", h2_style))
        if s7:
            for item in s7:
                elements.append(Paragraph(f"• {cls.escape_xml(item)}", body_style))
        else:
            elements.append(Paragraph("No se registraron no conformidades ni observaciones insubsanables en la oferta evaluada.", body_style))
        elements.append(Spacer(1, 4))

        # 8. Mejoras y Factores Diferenciadores Acreditados
        elements.append(Paragraph("8. Mejoras y Factores Diferenciadores Acreditados", h2_style))
        if s8:
            for item in s8:
                elements.append(Paragraph(f"• {cls.escape_xml(item)}", body_style))
        else:
            elements.append(Paragraph("La propuesta seleccionada no acreditó mejoras técnicas adicionales sobre las especificaciones base.", body_style))
        elements.append(Spacer(1, 4))

        # 9. Condiciones Comerciales y Contractuales Reales
        elements.append(Paragraph("9. Condiciones Comerciales y Contractuales", h2_style))
        conditions_list = s9.get("conditions", []) if isinstance(s9, dict) else []
        if conditions_list:
            s9_data = [[
                Paragraph("Condición", bold_style),
                Paragraph("Requerido", bold_style),
                Paragraph("Ofertado", bold_style),
                Paragraph("Valor Final", bold_style),
                Paragraph("Regla", bold_style),
                Paragraph("Estado", bold_style)
            ]]
            for c in conditions_list:
                s9_data.append([
                    Paragraph(cls.escape_xml(c.get('label') or c.get('key', '-')), body_style),
                    Paragraph(f"{cls.escape_xml(str(c.get('required_value', '-')))} {cls.escape_xml(c.get('unit', ''))}", body_style),
                    Paragraph(f"{cls.escape_xml(str(c.get('offered_value', '-')))} {cls.escape_xml(c.get('unit', ''))}", body_style),
                    Paragraph(f"{cls.escape_xml(str(c.get('final_value', '-')))} {cls.escape_xml(c.get('unit', ''))}", body_style),
                    Paragraph(cls.escape_xml(c.get('resolution_rule', '-')), body_style),
                    Paragraph(cls.escape_xml(c.get('status', '-')), body_style),
                ])
            t9 = Table(s9_data, colWidths=[120, 85, 85, 85, 95, 60])
            t9.setStyle(table_base_style)
            elements.append(t9)
        else:
            elements.append(Paragraph("No se registraron condiciones contractuales específicas en el expediente.", body_style))
        elements.append(Spacer(1, 4))

        # 10. Comparación Económica y Value for Money (VfM)
        elements.append(Paragraph("10. Comparación Económica y Value for Money (VfM)", h2_style))
        vfm_list = s10 or snapshot.get("vfm_evaluation", [])
        if vfm_list:
            s10_data = [[
                Paragraph("Proveedor", bold_style),
                Paragraph("Precio", bold_style),
                Paragraph("Puntaje", bold_style),
                Paragraph("Ratio VfM", bold_style),
                Paragraph("Elegible", bold_style),
                Paragraph("Orden", bold_style),
                Paragraph("Observación", bold_style)
            ]]
            for v in vfm_list:
                s_ratio = cls.format_decimal(v.get('vfm_ratio'), 4)
                s10_data.append([
                    Paragraph(f"{cls.escape_xml(v.get('supplier_name', '-'))}<br/><font color='#64748B'>{cls.escape_xml(v.get('supplier_ruc', '-'))}</font>", body_style),
                    Paragraph(f"{cls.escape_xml(v.get('currency', 'PEN'))} {cls.format_money(v.get('price', 0.0))}", body_style),
                    Paragraph(cls.format_decimal(v.get('total_score', 0.0), 2), body_style),
                    Paragraph(s_ratio, body_style),
                    Paragraph("Sí" if v.get("is_eligible") else "No", body_style),
                    Paragraph(cls.escape_xml(str(v.get("derived_rank", "-"))), body_style),
                    Paragraph(cls.escape_xml(v.get("reason", "")), body_style)
                ])
            t10 = Table(s10_data, colWidths=[140, 80, 50, 60, 45, 40, 115])
            t10.setStyle(table_base_style)
            elements.append(t10)
        else:
            elements.append(Paragraph("No se registraron ofertas en la evaluación VfM.", body_style))
        elements.append(Spacer(1, 4))

        # 11. Motivación y Cadena de Selección Interna
        elements.append(Paragraph("11. Motivación y Cadena de Selección Interna", h2_style))
        motivation_text = s11.get('motivation_text') or "El análisis sustenta el principio de eficacia, transparencia y debida motivación del procedimiento."
        elements.append(Paragraph(
            f"Propuesta adjudicada: <b>{cls.escape_xml(winner_sup_name)}</b> (RUC: {cls.escape_xml(winner_ruc)}), "
            f"por un monto total de <b>{cls.escape_xml(winner_curr)} {winner_amount}</b>.<br/>"
            f"<b>Motivación técnica y decisional:</b> {cls.escape_xml(motivation_text)}",
            body_style
        ))
        elements.append(Spacer(1, 4))

        # 12. Conclusión, Alcance Legal, Firmas y Auditoría
        elements.append(KeepTogether([
            Paragraph("12. Conclusión, Alcance Legal, Firmas y Auditoría", h2_style),
            Paragraph(
                "<b>AVISO LEGAL VINCULANTE:</b> La aprobación interna de este informe técnico de evaluación y selección interna no constituye otorgamiento de la buena pro, adjudicación ni perfeccionamiento del contrato.",
                legal_style
            ),
            Spacer(1, 4),
            Table([
                [Paragraph("Elaborado Por:", bold_style), Paragraph(cls.escape_xml(approval_meta.get("generated_by_name", "Operador")), body_style), Paragraph("Fecha:", bold_style), Paragraph(cls.escape_xml(approval_meta.get("generated_at", "-")), body_style)],
                [Paragraph("Aprobado Por:", bold_style), Paragraph(cls.escape_xml(approval_meta.get("approved_by_name", "Supervisor")), body_style), Paragraph("Fecha:", bold_style), Paragraph(cls.escape_xml(approval_meta.get("approved_at", "-")), body_style)],
                [Paragraph("Notas Aprobación:", bold_style), Paragraph(cls.escape_xml(approval_meta.get("approval_notes", "Conforme")), body_style), Paragraph("Hash Snapshot:", bold_style), Paragraph(f"<code>{cls.escape_xml(approval_meta.get('snapshot_hash', '-')[:24])}...</code>", body_style)],
            ], colWidths=[90, 180, 80, 180], style=[
                ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#F1F5F9')),
                ('INNERGRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#CBD5E1')),
                ('BOX', (0, 0), (-1, -1), 0.5, colors.HexColor('#94A3B8')),
                ('TOPPADDING', (0, 0), (-1, -1), 3),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
            ])
        ]))

        snap_hash = approval_meta.get("snapshot_hash", "NO_HASH")
        doc.build(
            elements,
            canvasmaker=lambda *args, **kwargs: NumberedCanvas(*args, snapshot_hash=snap_hash, **kwargs)
        )

        pdf_bytes = buffer.getvalue()
        buffer.close()

        # Validación con PyMuPDF (fitz)
        cls._verify_pdf_with_fitz(pdf_bytes)

        pdf_hash = hashlib.sha256(pdf_bytes).hexdigest()
        return pdf_bytes, pdf_hash

    @classmethod
    def _verify_pdf_with_fitz(cls, pdf_bytes: bytes) -> None:
        """
        Asegura que el PDF generado sea sintácticamente válido y contenga páginas y texto.
        """
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        if doc.page_count < 1:
            raise ValueError("El PDF generado no contiene páginas.")
        
        # Validar que al menos la primera página tenga texto
        page = doc.load_page(0)
        text = page.get_text()
        if not text or len(text.strip()) < 20:
            raise ValueError("El PDF generado carece de contenido textual verificable.")
        doc.close()

    @classmethod
    def persist_pdf_atomically(
        cls,
        pdf_bytes: bytes,
        target_directory: str,
        filename: str
    ) -> str:
        """
        Persiste los bytes del PDF de manera durable y atómica mediante archivo temporal,
        fsync, os.replace, realpath y commonpath anti-traversal.
        Retorna la ruta absoluta del archivo publicado.
        """
        os.makedirs(target_directory, exist_ok=True)
        real_root = os.path.realpath(target_directory)

        # Prevenir path traversal con realpath y commonpath
        candidate_path = os.path.normpath(os.path.join(real_root, filename))
        real_final = os.path.realpath(candidate_path)

        if os.path.commonpath([real_root, real_final]) != real_root:
            raise ValueError("Intento de path traversal detectado en nombre de archivo PDF.")

        # Prohibir enlaces simbólicos
        if os.path.islink(candidate_path) or os.path.islink(real_root):
            raise ValueError("No se permiten enlaces simbólicos en rutas de almacenamiento de reportes.")

        temp_filename = f".tmp_{uuid.uuid4().hex}_{filename}"
        temp_path = os.path.join(real_root, temp_filename)

        try:
            with open(temp_path, "wb") as f:
                f.write(pdf_bytes)
                f.flush()
                os.fsync(f.fileno())

            # Publicación atómica en el mismo sistema de archivos
            os.replace(temp_path, real_final)

            # Intentar fsync del directorio contenedor en sistemas compatibles (POSIX)
            try:
                dir_fd = os.open(real_root, os.O_RDONLY)
                try:
                    os.fsync(dir_fd)
                finally:
                    os.close(dir_fd)
            except (AttributeError, OSError, PermissionError):
                pass

            return real_final
        except Exception as e:
            if os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except OSError:
                    pass
            raise RuntimeError(f"Fallo al publicar el archivo PDF de forma atómica: {e}")

    @classmethod
    def reconcile_orphans(cls, target_directory: str, valid_paths: Optional[List[str]] = None, max_age_seconds: int = 300) -> int:
        """
        R3-09: Protocolo de reconciliación post-fallo con protección fail-safe:
        - Elimina archivos temporales huérfanos .tmp_* con antigüedad >= max_age_seconds.
        - Elimina archivos PDF no referenciados SOLAMENTE si valid_paths se proporciona explícitamente como lista no vacía.
        - Si valid_paths es None o vacío, NUNCA elimina archivos .pdf (protección fail-safe contra purgas accidentales).
        """
        if not os.path.exists(target_directory):
            return 0
        import time
        now = time.time()
        cleaned = 0
        real_root = os.path.realpath(target_directory)

        # Fail-safe: si no hay lista de rutas válidas explícita, no tocar archivos .pdf definitivos
        allow_pdf_reap = bool(valid_paths and len(valid_paths) > 0)
        valid_real_paths = {os.path.realpath(p) for p in valid_paths if p} if allow_pdf_reap else set()

        for fname in os.listdir(real_root):
            fpath = os.path.join(real_root, fname)
            if not os.path.isfile(fpath):
                continue

            # 1. Archivo temporal huérfano (.tmp_*)
            if fname.startswith(".tmp_"):
                try:
                    if now - os.path.getmtime(fpath) >= max_age_seconds:
                        os.remove(fpath)
                        cleaned += 1
                except OSError:
                    pass
                continue

            # 2. Archivo PDF huérfano (solo si allow_pdf_reap es True)
            if allow_pdf_reap and fname.startswith("report_p13_v") and fname.endswith(".pdf"):
                real_fpath = os.path.realpath(fpath)
                if real_fpath not in valid_real_paths:
                    try:
                        if now - os.path.getmtime(fpath) >= max_age_seconds:
                            os.remove(fpath)
                            cleaned += 1
                    except OSError:
                        pass

        return cleaned

    @classmethod
    def reconcile_all_orphans(cls, db: Any, target_directory: str, max_age_seconds: int = 3600) -> int:
        """
        R3-09: Reconciliación durable integrada: consulta directamente a la base de datos
        los informes aprobados con pdf_storage_path válido y limpia únicamente temporales
        y archivos PDF abandonados anteriores a max_age_seconds sin fila en base de datos.
        """
        if not os.path.exists(target_directory):
            return 0

        from app.models.v6.generated_output import GeneratedOutput
        active_paths_rows = (
            db.query(GeneratedOutput.pdf_storage_path)
            .filter(GeneratedOutput.pdf_storage_path != None)
            .all()
        )
        valid_paths = [r[0] for r in active_paths_rows if r[0]]

        total_cleaned = 0
        real_root = os.path.realpath(target_directory)
        for root, dirs, files in os.walk(real_root):
            cleaned = cls.reconcile_orphans(root, valid_paths=valid_paths, max_age_seconds=max_age_seconds)
            total_cleaned += cleaned

        return total_cleaned

    @classmethod
    def cleanup_stale_temp_files(cls, target_directory: str, max_age_seconds: int = 3600) -> int:
        """
        Limpia archivos temporales huérfanos .tmp_* en el directorio de almacenamiento
        sin purgar archivos PDF definitivos.
        """
        return cls.reconcile_orphans(target_directory, None, max_age_seconds=max_age_seconds)
