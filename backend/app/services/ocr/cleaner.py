import re
import difflib
from typing import List

EXPECTED_SUBTITLES = [
    r"5\.1\s+Descripción y cantidad de los bienes",
    r"5\.2\s+Características técnicas",
    r"5\.3\s+Embalaje y rotulado",
    r"5\.4\s+Transporte",
    r"5\.12\s+Garantía comercial",
    r"8\.1\s+Lugar de entrega",
    r"8\.2\s+Plazo",
    r"Objetivo General",
    r"Objetivos Específicos",
    r"Productos o entregables",
    r"Resultados esperados",
    r"Lugar y plazo",
    r"Forma de pago",
    r"Penalidades",
    r"Garantía comercial",
    r"Garantía",
    r"Descripción",
    r"Alcance",
    r"Condiciones",
    r"Requisitos",
    r"Lugar de entrega",
    r"Plazo"
]

def remove_repeated_headers_footers(pages_text: List[str]) -> str:
    """
    Elimina textos repetitivos (encabezados, pies de página, número de página)
    evaluando la lista de páginas y detectando líneas idénticas al inicio y final.
    """
    if not pages_text:
        return ""
        
    cleaned_pages = []
    
    # Expresiones regulares comunes para basura (ej. "Página 1 de 9", logos textuales, etc.)
    page_regex = re.compile(r'P[áa]gina\s+\d+\s+de\s+\d+', re.IGNORECASE)
    
    # 1. Limpieza obvia por regex en todas las páginas
    for page in pages_text:
        lines = page.split('\n')
        new_lines = []
        for line in lines:
            s_line = line.strip()
            # Eliminar "Página X de Y"
            if page_regex.search(s_line):
                continue
            # Eliminar membretes comunes si son toda la línea
            if re.match(r'^(GOBIERNO REGIONAL|DIRECCIÓN REGIONAL|MINISTERIO DE|MUNICIPALIDAD).{0,50}$', s_line, re.IGNORECASE):
                continue
            new_lines.append(line)
        cleaned_pages.append("\n".join(new_lines))
        
    return "\n".join(cleaned_pages)

def clean_ocr_text(text: str) -> str:
    """
    Realiza limpieza técnica de texto proveniente de OCR.
    Mantiene intacto el sentido original.
    """
    if not text:
        return ""
        
    # 0. Eliminar marcadores de plantilla
    text = re.sub(r'\(obligatorio\)', '', text, flags=re.IGNORECASE)
    text = re.sub(r'\(de corresponder\)', '', text, flags=re.IGNORECASE)
    
    # También limpiar versiones sin paréntesis si están sueltas (pero cuidado con afectar texto real).
    # Mejor ser conservador y usar el lookbehind para espacios
    text = re.sub(r'\b(obligatorio)\b', '', text, flags=re.IGNORECASE)
    text = re.sub(r'\b(de corresponder)\b', '', text, flags=re.IGNORECASE)
    
    # 1. Unir palabras partidas por guiones al final de línea
    # Ej: "computado-\nras" -> "computadoras"
    cleaned = re.sub(r'([a-záéíóúñA-ZÁÉÍÓÚÑ])-\s*\n\s*([a-záéíóúñA-ZÁÉÍÓÚÑ])', r'\1\2', text)
    
    # 2. Corregir saltos de línea innecesarios dentro de párrafos.
    cleaned = re.sub(r'(?<!\n)\n(?=[a-záéíóúñ](?!\)))', ' ', cleaned)
    
    # 3. Eliminar espacios múltiples
    cleaned = re.sub(r' {2,}', ' ', cleaned)
    
    # 4. Eliminar artefactos de OCR comunes (caracteres basura sueltos)
    cleaned = re.sub(r'^[^\w\s]{2,}\s*$', '', cleaned, flags=re.MULTILINE)
    
    # Normalizar viñetas extrañas a guiones estándar para listas
    # El problema fue que re.sub no soporta `^|\n` de tamaño variable en un lookbehind.
    # En lugar de lookbehind, usamos una expresión regular normal capturando y reemplazando.
    cleaned = re.sub(r'(^|\n)\s*[+o•*]\s+', r'\1- ', cleaned)
    
    # 5. Estandarizar saltos de párrafo (reducir 3+ saltos a 2)
    cleaned = re.sub(r'\n{3,}', '\n\n', cleaned)
    
    return cleaned.strip()

def normalize_structural_breaks(text: str) -> str:
    """
    Inserta saltos de línea antes de patrones estructurales anidados
    (como numerales, literales, viñetas) y separa títulos esperados
    del párrafo subsiguiente.
    """
    if not text:
        return ""

    # 1. Insert breaks BEFORE structural inline items
    # Romanos (exigir punto después del romano para evitar falsos positivos)
    text = re.sub(r'(?<!\w)(I|II|III|IV|V|VI|VII|VIII|IX|X|XI|XII|XIII|XIV)\.\s+(?=[A-ZÁÉÍÓÚÑ])', r'\n\1. ', text)
    
    # Numerales decimales (ej 5.1, 5.12, 1.1.1)
    text = re.sub(r'(?<![\d,])(\d+\.\d+(?:\.\d+)?)(?![\d,])\s+(?=[A-ZÁÉÍÓÚÑ])', r'\n\1 ', text)
    
    # Literales (a), b), etc)
    text = re.sub(r'(?<=\s)([a-z]\))\s+', r'\n\1 ', text)
    
    # Viñetas (ahora todas normalizadas a guion por clean_ocr_text)
    text = re.sub(r'(?<=\s)([-])\s+', r'\n\1 ', text)
    
    # 2. Separate known titles from paragraph
    for subtitle_regex in EXPECTED_SUBTITLES:
        pattern = re.compile(rf'({subtitle_regex})\s*(?=[A-ZÁÉÍÓÚÑ\d])', re.IGNORECASE)
        text = pattern.sub(r'\1\n', text)
        
    # Clean up excessive newlines
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()
