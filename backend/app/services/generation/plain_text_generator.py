from typing import List, Dict, Any

def generate_plain_text(sections: List[Dict[str, Any]], comparison_results: List[Dict[str, Any]] = None) -> str:
    """
    Genera salida en texto plano de las secciones y tabla de comparación.
    """
    lines = []
    
    # 1. Secciones
    for sec in sorted(sections, key=lambda x: x.get('original_order', 0)):
        roman = sec.get('original_roman', '')
        title = sec.get('title', '')
        content = sec.get('current_text', '')
        
        lines.append(f"{roman}. {title}")
        
        structure = sec.get('structure_json')
        if structure and isinstance(structure, list) and len(structure) > 0:
            for block in structure:
                block_type = block.get('type')
                text_content = block.get('text', '')
                label = block.get('label', '')
                
                if block_type == 'subsection_title':
                    label_str = f"{label} " if label else ""
                    lines.append(f"\n{label_str}{text_content}\n")
                elif block_type == 'paragraph':
                    lines.append(text_content)
                elif block_type == 'numbered_item':
                    indent = "  " * block.get('level', 1)
                    lines.append(f"{indent}{label} {text_content}")
                elif block_type in ('letter_item', 'bullet_item'):
                    lines.append(f"  {label} {text_content}")
                else:
                    lines.append(text_content)
        else:
            lines.append(content)
            
        lines.append("-" * 40)
        
    # 2. Comparación
    if comparison_results:
        lines.append("\nCUADRO COMPARATIVO DE CONDICIONES")
        lines.append("=" * 60)
        for row in comparison_results:
            field = row.get('field_name', '')
            final = row.get('final_value') or '-'
            status = row.get('status', '')
            lines.append(f"{field.upper()}: {final} ({status})")
            
    return "\n".join(lines)
