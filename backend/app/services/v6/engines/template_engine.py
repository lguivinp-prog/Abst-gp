from typing import Dict, Any
import hashlib
from datetime import datetime, timezone

# Concept: TemplateVariableRegistry
TEMPLATE_VARIABLE_REGISTRY = {
    "supplier_name": {"source": "SupplierProfile.business_name", "evidence_required": True},
    "supplier_ruc": {"source": "SupplierProfile.ruc", "evidence_required": True},
    "contract_amount": {"source": "SupplierOffer.price", "evidence_required": False},
}

class OutputTemplateEngine:
    @staticmethod
    def render_template(template_content: str, data_snapshot: Dict[str, Any]) -> tuple[str, str]:
        """
        Renders the template using strictly the snapshot data.
        Returns a tuple of (rendered_content, hash).
        """
        rendered = template_content
        # Strict injection: only keys present in snapshot are replaced.
        # Format assumed: {{ variable_name }}
        for key, value in data_snapshot.items():
            if key in TEMPLATE_VARIABLE_REGISTRY:
                placeholder = f"{{{{ {key} }}}}"
                rendered = rendered.replace(placeholder, str(value))
                
        # Simple validation: if any placeholder remains, it means missing data.
        if "{{" in rendered and "}}" in rendered:
            raise ValueError("Template contains unresolved placeholders.")
            
        content_hash = hashlib.sha256(rendered.encode('utf-8')).hexdigest()
        return rendered, content_hash
