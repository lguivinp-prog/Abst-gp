import pytest
from app.services.generation.html_generator import generate_html

def test_html_rendering_justified():
    sections = [
        {
            "original_roman": "I",
            "title": "FINALIDAD PÚBLICA",
            "current_text": "El requerimiento es necesario.",
            "structure_json": [
                {
                    "type": "paragraph",
                    "text": "El requerimiento es necesario."
                }
            ],
            "is_selected": True
        }
    ]
    html_output = generate_html(sections, [])
    # Verify that the generated HTML has the correct justification styles
    assert 'text-align: justify;' in html_output
    assert 'text-justify: inter-word;' in html_output
    assert 'line-height: 1.6;' in html_output
