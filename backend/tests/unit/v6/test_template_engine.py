import pytest
from app.services.v6.engines.template_engine import OutputTemplateEngine

def test_template_engine_renders_strictly():
    template = "El proveedor {{ supplier_name }} con RUC {{ supplier_ruc }} proveera."
    snapshot = {"supplier_name": "Tech Corp", "supplier_ruc": "20123456789"}
    
    rendered, hash_val = OutputTemplateEngine.render_template(template, snapshot)
    assert "Tech Corp" in rendered
    assert "20123456789" in rendered
    assert "{{" not in rendered
    assert hash_val is not None

def test_template_engine_fails_on_missing_data():
    template = "El proveedor {{ supplier_name }} con RUC {{ supplier_ruc }} proveera."
    snapshot = {"supplier_name": "Tech Corp"} # Missing RUC
    
    with pytest.raises(ValueError, match="unresolved placeholders"):
        OutputTemplateEngine.render_template(template, snapshot)
