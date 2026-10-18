import re
import html
import hashlib
from decimal import Decimal
import bleach
from typing import Dict, Any, Tuple, List, Set

class ReportTemplateEngine:
    """
    Motor seguro de renderizado de plantillas HTML para informes P13 con validación estricta.
    Garantiza:
    - Verificación fail-closed de placeholders: cualquier placeholder desconocido o no definido
      en la plantilla provoca ValueError antes de cualquier persistencia (emulación estricta).
    - Soporte completo para las 12 secciones estructurales canónicas acordadas en Issue #14.
    - Escape contextual de valores dinámicos para mitigar Cross-Site Scripting (XSS).
    - Sanitización estructural mediante bleach con lista blanca de etiquetas HTML seguras.
    - Cálculo determinista del hash SHA-256 sobre los bytes UTF-8 exactos resultantes.
    """

    ALLOWED_TAGS = [
        'div', 'span', 'p', 'h1', 'h2', 'h3', 'h4', 'table', 'thead', 'tbody',
        'tr', 'th', 'td', 'ul', 'ol', 'li', 'strong', 'em', 'b', 'i', 'hr', 'br',
        'section', 'header', 'footer', 'small', 'blockquote'
    ]
    ALLOWED_ATTRIBUTES = {
        '*': ['class', 'id'],
        'th': ['colspan', 'rowspan'],
        'td': ['colspan', 'rowspan']
    }

    @classmethod
    def escape_value(cls, val: Any) -> str:
        if val is None:
            return ""
        return html.escape(str(val), quote=True)

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
    def _build_12_sections_html(cls, snapshot: Dict[str, Any], approval_meta: Dict[str, Any]) -> Dict[str, str]:
        """
        Construye el contenido HTML estructurado para cada una de las 12 secciones de P13.
        """
        metadata = snapshot.get("metadata", {})
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
        s12 = snapshot.get("section_12_conclusion_audit", {})

        # Sección 1: Expediente y Objeto
        s1_html = (
            "<table class=\"report-table\">\n"
            f"  <tr><th>Código / SIGA</th><td>{cls.escape_value(s1.get('case_code', metadata.get('case_code', '-')))}</td></tr>\n"
            f"  <tr><th>Título / Objeto</th><td>{cls.escape_value(s1.get('object_title', '-'))}</td></tr>\n"
            f"  <tr><th>Tipo de Contratación</th><td>{cls.escape_value(s1.get('contract_type', '-'))}</td></tr>\n"
            f"  <tr><th>Entidad / Dependencia</th><td>{cls.escape_value(s1.get('entity_name', 'Entidad Convocante'))}</td></tr>\n"
            "</table>"
        )

        # Sección 2: Antecedentes Administrativos
        s2_html = (
            f"<p><strong>Estado del Flujo:</strong> {cls.escape_value(s2.get('workflow_status', 'APPROVED'))}</p>\n"
            f"<p><strong>Régimen Normativo Aplicable:</strong> {cls.escape_value(s2.get('legal_regime_notice', snapshot.get('legal_regime_notice', '-')))}</p>\n"
            f"<p><strong>Resumen de Antecedentes:</strong> {cls.escape_value(s2.get('summary', 'Expediente tramitado y verificado conforme al flujo institucional.'))}</p>"
        )

        # Sección 3: Documentos Examinados y Hashes Sustentados
        if s3:
            s3_rows = []
            for doc in s3:
                s3_rows.append(
                    f"<tr><td>{cls.escape_value(doc.get('id', '-'))}</td>"
                    f"<td>{cls.escape_value(doc.get('filename', '-'))}</td>"
                    f"<td>{cls.escape_value(doc.get('document_type', '-'))}</td>"
                    f"<td>{cls.escape_value(doc.get('mime_type', '-'))}</td>"
                    f"<td><code>{cls.escape_value(doc.get('sha256', doc.get('status', 'REGISTRADO')))}</code></td></tr>"
                )
            s3_html = (
                "<table class=\"report-table\">\n"
                "  <thead><tr><th>ID</th><th>Archivo</th><th>Tipo</th><th>MIME</th><th>Checksum / Estado</th></tr></thead>\n"
                f"  <tbody>\n{''.join(s3_rows)}\n  </tbody>\n</table>"
            )
        else:
            s3_html = "<p>No se registraron documentos anexos en el expediente.</p>"

        # Sección 4: Proveedores Participantes y Ofertas
        if s4:
            s4_rows = []
            for off in s4:
                s4_rows.append(
                    f"<tr><td>{cls.escape_value(off.get('supplier_name', '-'))}</td>"
                    f"<td>{cls.escape_value(off.get('supplier_ruc', '-'))}</td>"
                    f"<td>{cls.escape_value(off.get('currency', 'PEN'))} {cls.escape_value(cls.format_money(off.get('total_amount', 0.0)))}</td>"
                    f"<td>{cls.escape_value(off.get('status', '-'))}</td></tr>"
                )
            s4_html = (
                "<table class=\"report-table\">\n"
                "  <thead><tr><th>Proveedor</th><th>RUC</th><th>Monto Ofertado</th><th>Estado</th></tr></thead>\n"
                f"  <tbody>\n{''.join(s4_rows)}\n  </tbody>\n</table>"
            )
        else:
            s4_html = "<p>No se registraron otras ofertas participantes.</p>"

        # Sección 5: Matriz de Evaluación Técnica y Requisitos
        reqs = s5 or snapshot.get("requirements", [])
        if reqs:
            s5_rows = []
            for r in reqs:
                mand_str = "Sí" if r.get("mandatory") else "No"
                s5_rows.append(
                    f"<tr><td>{cls.escape_value(r.get('description', '-'))}</td>"
                    f"<td>{mand_str}</td>"
                    f"<td>{cls.escape_value(r.get('evaluation_status', '-'))}</td></tr>"
                )
            s5_html = (
                "<table class=\"report-table\">\n"
                "  <thead><tr><th>Requisito</th><th>Obligatorio</th><th>Resultado Técnico</th></tr></thead>\n"
                f"  <tbody>\n{''.join(s5_rows)}\n  </tbody>\n</table>"
            )
        else:
            s5_html = "<p>No se registraron requisitos en la matriz técnica.</p>"

        # Sección 6: Trazabilidad de Evidencias Acreditadas
        evidences = s6 or []
        if evidences:
            s6_rows = []
            for ev in evidences:
                page_str = f"Pág. {cls.escape_value(str(ev.get('page')))}" if ev.get('page') is not None else "Sin pág."
                frag_str = f"\"{cls.escape_value(ev.get('fragment'))}\"" if ev.get('fragment') else "Sin fragmento"
                s6_rows.append(
                    f"<tr><td>{cls.escape_value(ev.get('requirement', '-'))}</td>"
                    f"<td>{cls.escape_value(ev.get('document_name', '-'))}</td>"
                    f"<td>{page_str}</td>"
                    f"<td><em>{frag_str}</em></td>"
                    f"<td>{cls.escape_value(ev.get('status', 'VERIFICADO'))}</td>"
                    f"<td>{cls.escape_value(ev.get('verified_by', '-'))}</td></tr>"
                )
            s6_html = (
                "<table class=\"report-table\">\n"
                "  <thead><tr><th>Requisito</th><th>Documento</th><th>Página</th><th>Fragmento Sustentatorio</th><th>Estado</th><th>Verificador</th></tr></thead>\n"
                f"  <tbody>\n{''.join(s6_rows)}\n  </tbody>\n</table>"
            )
        else:
            s6_html = "<p>No se registraron evidencias documentales trazadas en el expediente.</p>"

        # Sección 7: Resultados No Conformes y Revisión Humana
        if s7:
            s7_items = [f"<li>{cls.escape_value(item)}</li>" for item in s7]
            s7_html = f"<ul>{''.join(s7_items)}</ul>"
        else:
            s7_html = "<p>No se registraron no conformidades ni observaciones insubsanables en la oferta seleccionada.</p>"

        # Sección 8: Mejoras y Factores Diferenciadores
        if s8:
            s8_items = [f"<li>{cls.escape_value(item)}</li>" for item in s8]
            s8_html = f"<ul>{''.join(s8_items)}</ul>"
        else:
            s8_html = "<p>La oferta seleccionada no acreditó mejoras técnicas adicionales sobre los términos de referencia.</p>"

        # Sección 9: Condiciones Contractuales Reales
        conditions_list = s9.get("conditions", []) if isinstance(s9, dict) else []
        if conditions_list:
            s9_rows = []
            for c in conditions_list:
                s9_rows.append(
                    f"<tr><td><strong>{cls.escape_value(c.get('label') or c.get('key', '-'))}</strong></td>"
                    f"<td>{cls.escape_value(str(c.get('required_value', '-')))} {cls.escape_value(c.get('unit', ''))}</td>"
                    f"<td>{cls.escape_value(str(c.get('offered_value', '-')))} {cls.escape_value(c.get('unit', ''))}</td>"
                    f"<td>{cls.escape_value(str(c.get('final_value', '-')))} {cls.escape_value(c.get('unit', ''))}</td>"
                    f"<td>{cls.escape_value(c.get('resolution_rule', '-'))}</td>"
                    f"<td>{cls.escape_value(c.get('status', '-'))}</td></tr>"
                )
            s9_html = (
                "<table class=\"report-table\">\n"
                "  <thead><tr><th>Condición</th><th>Requerido</th><th>Ofertado</th><th>Valor Final</th><th>Regla</th><th>Estado</th></tr></thead>\n"
                f"  <tbody>\n{''.join(s9_rows)}\n  </tbody>\n</table>"
            )
        else:
            s9_html = "<p>No se registraron condiciones contractuales específicas en el expediente.</p>"

        # Sección 10: Comparación Económica y VfM
        vfm_list = s10 or snapshot.get("vfm_evaluation", [])
        if vfm_list:
            s10_rows = []
            for v in vfm_list:
                s_ratio = cls.format_decimal(v.get('vfm_ratio'), 4)
                s10_rows.append(
                    f"<tr><td>{cls.escape_value(v.get('supplier_name', '-'))} ({cls.escape_value(v.get('supplier_ruc', '-'))})</td>"
                    f"<td>{cls.escape_value(v.get('currency', 'PEN'))} {cls.escape_value(cls.format_money(v.get('price', 0.0)))}</td>"
                    f"<td>{cls.escape_value(cls.format_decimal(v.get('total_score', 0.0), 2))}</td>"
                    f"<td>{s_ratio}</td>"
                    f"<td>{'Elegible' if v.get('is_eligible') else 'No Elegible'}</td>"
                    f"<td>{cls.escape_value(str(v.get('derived_rank', '-')))}</td>"
                    f"<td>{cls.escape_value(v.get('reason', ''))}</td></tr>"
                )
            s10_html = (
                "<table class=\"report-table vfm-table\">\n"
                "  <thead><tr><th>Proveedor</th><th>Precio</th><th>Puntaje</th><th>Ratio VfM (P/S)</th><th>Elegibilidad</th><th>Orden</th><th>Observación</th></tr></thead>\n"
                f"  <tbody>\n{''.join(s10_rows)}\n  </tbody>\n</table>\n"
                f"<p class=\"text-xs text-gray-500 mt-1\">Algoritmo: {cls.escape_value(snapshot.get('vfm_algorithm_version', 'P11_VFM_V1'))}</p>"
            )
        else:
            s10_html = "<p>No se encontraron registros de evaluación VfM.</p>"

        # Sección 11: Motivación y Cadena de Selección Interna
        winner_name = winner.get("supplier_name", "-")
        winner_ruc = winner.get("supplier_ruc", "-")
        winner_curr = winner.get("currency", "PEN")
        winner_price = cls.format_money(winner.get('total_amount', 0.0))
        motivation_text = s11.get('motivation_text') or "Cumplimiento integral de los requerimientos técnicos y criterios de contratación pública."
        s11_html = (
            f"<p>Propuesta adjudicada: <strong>{cls.escape_value(winner_name)}</strong> (RUC: {cls.escape_value(winner_ruc)}), "
            f"por un importe total de <strong>{cls.escape_value(winner_curr)} {cls.escape_value(winner_price)}</strong>.</p>\n"
            f"<p><strong>Motivación técnica y decisional:</strong> {cls.escape_value(motivation_text)}</p>"
        )

        # Sección 12: Conclusión, Alcance Legal, Firmas y Auditoría
        s12_html = (
            "<div class=\"conclusion-box\">\n"
            "  <p><strong>CONCLUSIÓN:</strong> Se emite conformidad sobre la evaluación técnica y económica de la propuesta seleccionada.</p>\n"
            "  <div class=\"legal-warning\">\n"
            "    <p><strong>AVISO LEGAL VINCULANTE:</strong> La aprobación interna de este informe técnico de evaluación y selección interna no constituye otorgamiento de la buena pro, adjudicación ni perfeccionamiento del contrato.</p>\n"
            "  </div>\n"
            "  <div class=\"signatures-grid\">\n"
            f"    <p><strong>Elaborado por:</strong> {cls.escape_value(approval_meta.get('generated_by_name', 'Operador'))} ({cls.escape_value(approval_meta.get('generated_at', '-'))})</p>\n"
            f"    <p><strong>Aprobado por:</strong> {cls.escape_value(approval_meta.get('approved_by_name', 'Supervisor'))} ({cls.escape_value(approval_meta.get('approved_at', '-'))})</p>\n"
            f"    <p><strong>Notas de Aprobación:</strong> {cls.escape_value(approval_meta.get('approval_notes', 'Sin notas'))}</p>\n"
            f"    <p><strong>Hash de Integridad (Snapshot):</strong> <code>{cls.escape_value(approval_meta.get('snapshot_hash', '-'))}</code></p>\n"
            "  </div>\n"
            "</div>"
        )

        return {
            "section_1_case_object_html": s1_html,
            "section_2_antecedents_html": s2_html,
            "section_3_examined_documents_html": s3_html,
            "section_4_suppliers_offers_html": s4_html,
            "section_5_requirements_matrix_html": s5_html,
            "section_6_evidence_traceability_html": s6_html,
            "section_7_non_conformities_html": s7_html,
            "section_8_improvements_html": s8_html,
            "section_9_contractual_conditions_html": s9_html,
            "section_10_economic_vfm_html": s10_html,
            "section_11_motivation_selection_html": s11_html,
            "section_12_conclusion_audit_html": s12_html,
        }

    @classmethod
    def render_html(
        cls,
        template_content: str,
        snapshot: Dict[str, Any],
        approval_meta: Dict[str, Any]
    ) -> Tuple[str, str]:
        """
        Renderiza la plantilla interpolando variables del snapshot y metadatos de aprobación.
        Valida de forma estricta que todo placeholder en la plantilla exista en el contexto.
        Retorna (html_renderizado, html_hash).
        """
        # 1. Extraer todos los placeholders de la plantilla
        found_placeholders: Set[str] = set(re.findall(r'\{\{\s*([a-zA-Z0-9_]+)\s*\}\}', template_content))

        # 2. Preparar el mapa completo de variables permitidas y valores escapados
        winner = snapshot.get("winner", {})
        metadata = snapshot.get("metadata", {})

        sections_html = cls._build_12_sections_html(snapshot, approval_meta)

        gen_by = cls.escape_value(approval_meta.get("generated_by_name", "Sistema"))
        gen_at = cls.escape_value(approval_meta.get("generated_at", "-"))
        appr_by = cls.escape_value(approval_meta.get("approved_by_name", "Pendiente"))
        appr_at = cls.escape_value(approval_meta.get("approved_at", "Pendiente"))
        appr_notes = cls.escape_value(approval_meta.get("approval_notes", "Sin notas"))

        context: Dict[str, str] = {
            # Metadatos del expediente
            "case_code": cls.escape_value(metadata.get("case_code", "-")),
            "version_number": cls.escape_value(str(metadata.get("version_number", 1))),
            "legal_regime_notice": cls.escape_value(snapshot.get("legal_regime_notice", "Régimen normativo específico no determinado; requiere validación administrativa.")),

            # Ganador
            "selected_supplier_name": cls.escape_value(winner.get("supplier_name", "-")),
            "selected_supplier_ruc": cls.escape_value(winner.get("supplier_ruc", "-")),
            "selected_supplier_status": cls.escape_value(winner.get("validation_status", "-")),
            "currency": cls.escape_value(winner.get("currency", "PEN")),
            "total_amount": cls.escape_value(cls.format_money(winner.get('total_amount', 0.0))),

            # Tablas legadas (compatibilidad)
            "requirements_table_html": sections_html["section_5_requirements_matrix_html"],
            "vfm_table_html": sections_html["section_10_economic_vfm_html"],
            "vfm_algorithm_version": cls.escape_value(snapshot.get("vfm_algorithm_version", "P11_VFM_V1")),

            # Metadatos de aprobación y auditoría
            "generated_by_name": gen_by,
            "generated_at": gen_at,
            "approved_by_name": appr_by,
            "approved_at": appr_at,
            "approval_notes": appr_notes,
            "snapshot_hash": cls.escape_value(approval_meta.get("snapshot_hash", "-")),

            # 12 Secciones estructurales canónicas
            **sections_html
        }

        # 3. Validación estricta fail-closed de placeholders
        unknown_placeholders = found_placeholders - set(context.keys())
        if unknown_placeholders:
            sorted_unknown = sorted(list(unknown_placeholders))
            raise ValueError(
                f"Error en plantilla: placeholders no reconocidos o indefinidos detectados: {sorted_unknown}"
            )

        # 4. Sustitución de placeholders verificados
        rendered = template_content
        for key, val in context.items():
            pattern = re.compile(r'\{\{\s*' + re.escape(key) + r'\s*\}\}')
            rendered = pattern.sub(str(val), rendered)

        # Comprobar si aún quedan marcadores sin sustituir
        leftovers = re.findall(r'\{\{\s*[^}]+\s*\}\}', rendered)
        if leftovers:
            raise ValueError(f"Error de renderizado: marcadores no resueltos en la plantilla: {leftovers}")

        # 5. Sanitizar mediante bleach
        clean_html = bleach.clean(
            rendered,
            tags=cls.ALLOWED_TAGS,
            attributes=cls.ALLOWED_ATTRIBUTES,
            strip=False
        )

        html_bytes = clean_html.encode('utf-8')
        html_hash = hashlib.sha256(html_bytes).hexdigest()

        return clean_html, html_hash
