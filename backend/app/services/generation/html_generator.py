import html
from typing import List, Dict, Any

def generate_html(sections: List[Dict[str, Any]], comparison_results: List[Dict[str, Any]] = None) -> str:
    """
    Genera un HTML limpio y sanitizado a partir de las secciones procesadas.
    Permite copiar hacia Word u otros sistemas sin estilos peligrosos.
    """
    html_lines = [
        '<div class="abst-document" style="font-family: Arial, sans-serif; line-height: 1.5; color: #000;">'
    ]
    
    # 1. Imprimir las secciones ordenadas con su número romano original
    for sec in sorted(sections, key=lambda x: x.get('original_order', 0)):
        roman = html.escape(sec.get('original_roman', ''))
        title = html.escape(sec.get('title', ''))
        content = html.escape(sec.get('current_text', ''))
        
        html_lines.append(
            f'<h3 style="margin-top: 1em; margin-bottom: 0.5em; font-size: 1.2em; font-weight: bold;">{roman}. {title}</h3>'
        )
        
        structure = sec.get('structure_json')
        if structure and isinstance(structure, list) and len(structure) > 0:
            for block in structure:
                block_type = block.get('type')
                text_content = html.escape(block.get('text', ''))
                label = html.escape(block.get('label', ''))
                
                if block_type == 'subsection_title':
                    level = block.get("level", 1)
                    font_size = "1.2em" if level == 1 else "1.1em" if level == 2 else "1em"
                    label_str = f"{label} " if label else ""
                    html_lines.append(f'<h4 style="margin-top: 1em; margin-bottom: 0.5em; font-size: {font_size}; font-weight: bold;">{label_str}{text_content}</h4>')
                elif block_type == 'paragraph':
                    html_lines.append(f'<p style="text-align: justify; text-justify: inter-word; line-height: 1.6; margin-top: 0; margin-bottom: 0.75rem;">{text_content}</p>')
                elif block_type == 'numbered_item':
                    html_lines.append(f'<div style="margin-left: {block.get("level", 1) * 20}px; margin-bottom: 0.5em; text-align: justify;"><strong>{label}</strong> {text_content}</div>')
                elif block_type == 'letter_item':
                    html_lines.append(f'<div style="margin-left: 40px; margin-bottom: 0.5em; text-align: justify;"><strong>{label}</strong> {text_content}</div>')
                elif block_type == 'bullet_item':
                    html_lines.append(f'<div style="margin-left: 40px; margin-bottom: 0.5em; text-align: justify;">- {text_content}</div>')
                elif block_type == 'table_vertical':
                    rows = block.get('rows', [])
                    html_lines.append('<table style="width: 100%; border-collapse: collapse; margin-bottom: 1em; font-size: 0.9em;"><tbody>')
                    for row in rows:
                        for k, v in row.items():
                            k_esc = html.escape(str(k))
                            if isinstance(v, list):
                                html_lines.append(f'<tr><td style="border: 1px solid #ccc; padding: 6px; font-weight: bold; width: 30%; vertical-align: top;">{k_esc}</td><td style="border: 1px solid #ccc; padding: 6px; vertical-align: top;"><ul style="margin:0; padding-left:20px;">')
                                for item in v:
                                    html_lines.append(f'<li>{html.escape(str(item))}</li>')
                                html_lines.append('</ul></td></tr>')
                            else:
                                html_lines.append(f'<tr><td style="border: 1px solid #ccc; padding: 6px; font-weight: bold; width: 30%; vertical-align: top;">{k_esc}</td><td style="border: 1px solid #ccc; padding: 6px; vertical-align: top;">{html.escape(str(v))}</td></tr>')
                    html_lines.append('</tbody></table>')
                elif block_type == 'warning':
                    html_lines.append(f'<div style="margin-top: 1em; margin-bottom: 1em; padding: 10px; border-left: 4px solid #ffcc00; background-color: #fff9e6; color: #856404;"><strong>Advertencia:</strong> {text_content}</div>')
                else:
                    html_lines.append(f'<p style="text-align: justify; text-justify: inter-word; line-height: 1.6; margin-top: 0; margin-bottom: 0.75rem;">{text_content}</p>')
        else:
            # Fallback to current text if no structure
            content = html.escape(sec.get('current_text', ''))
            for para in content.split('\n'):
                if para.strip():
                    html_lines.append(f'<p style="text-align: justify; text-justify: inter-word; line-height: 1.6; margin-top: 0; margin-bottom: 0.75rem;">{para}</p>')
        
    # 2. Agregar tabla comparativa si hay resultados
    if comparison_results:
        html_lines.append('<hr style="margin: 2em 0; border: 1px solid #ccc;"/>')
        html_lines.append('<h3 style="font-weight: bold;">Cuadro Comparativo de Condiciones</h3>')
        
        table_html = [
            '<table style="width: 100%; border-collapse: collapse; margin-bottom: 2em;">',
            '<thead>',
            '<tr>',
            '<th style="border: 1px solid #000; padding: 8px; background-color: #f2f2f2;">Campo</th>',
            '<th style="border: 1px solid #000; padding: 8px; background-color: #f2f2f2;">Requerimiento</th>',
            '<th style="border: 1px solid #000; padding: 8px; background-color: #f2f2f2;">Cotización</th>',
            '<th style="border: 1px solid #000; padding: 8px; background-color: #f2f2f2;">Resultado Final</th>',
            '<th style="border: 1px solid #000; padding: 8px; background-color: #f2f2f2;">Estado</th>',
            '</tr>',
            '</thead>',
            '<tbody>'
        ]
        
        for row in comparison_results:
            field = html.escape(str(row.get('field_name', '')))
            req = html.escape(str(row.get('requirement_value') or '-'))
            quot = html.escape(str(row.get('quotation_value') or '-'))
            final = html.escape(str(row.get('final_value') or '-'))
            status = html.escape(str(row.get('status', '')))
            
            table_html.append('<tr>')
            table_html.append(f'<td style="border: 1px solid #000; padding: 8px;">{field}</td>')
            table_html.append(f'<td style="border: 1px solid #000; padding: 8px;">{req}</td>')
            table_html.append(f'<td style="border: 1px solid #000; padding: 8px;">{quot}</td>')
            table_html.append(f'<td style="border: 1px solid #000; padding: 8px; font-weight: bold;">{final}</td>')
            table_html.append(f'<td style="border: 1px solid #000; padding: 8px;">{status}</td>')
            table_html.append('</tr>')
            
        table_html.append('</tbody></table>')
        html_lines.extend(table_html)
        
    html_lines.append('</div>')
    return "\n".join(html_lines)
