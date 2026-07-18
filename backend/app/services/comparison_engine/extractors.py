import re
from typing import Optional, Tuple

def extract_numeric_value(text: str) -> Optional[Tuple[float, Optional[str]]]:
    # Regex para extraer un número (con miles y decimales) y opcionalmente su unidad.
    # Explicación:
    # (?<![a-zA-Z\d])      : No debe estar precedido por una letra ni un dígito (ej. rechaza IP65 y partes de números).
    # (                    : Grupo 1 - El número.
    #   -?                 : Opcional signo negativo.
    #   (?:
    #     \d{1,3}(?:[.,]\d{3})+(?:[.,]\d+)? | # Formato con separadores de miles (ej. 1,000.50 o 1.000,50)
    #     \d+(?:[.,]\d+)?                     # Formato simple sin miles (ej. 1000.50 o 1000)
    #   )
    # )
    # (?!\d)               : No seguido de un dígito.
    # \s*                  : Espacios opcionales.
    # ([a-zA-Z]+)?         : Grupo 2 - La unidad de medida (letras opcionales).
    
    # Pre-compilamos regex
    pattern = re.compile(r'(?<![a-zA-Z\d])(-?(?:\d{1,3}(?:[.,]\d{3})+(?:[.,]\d+)?|\d+(?:[.,]\d+)?))(?!\d)\s*([a-zA-Z]+)?')
    
    # Buscar todos los matches
    matches = pattern.finditer(text)
    
    # Blacklist de palabras anteriores que indican un modelo/estándar, no magnitud.
    blacklist_prev_words = {"aisi", "iso", "iec", "astm", "din", "en", "sae"}
    
    for match in matches:
        number_str = match.group(1)
        unit = match.group(2)
        
        # Verificar la palabra anterior para descartar "AISI 304", etc.
        start_idx = match.start()
        if start_idx > 0:
            # Buscar la palabra justo antes del número
            prev_text = text[:start_idx].strip()
            if prev_text:
                last_word = prev_text.split()[-1].lower()
                if last_word in blacklist_prev_words:
                    continue # Saltar al siguiente match
                    
        # Normalizar el string del número a float válido en Python
        # Si tiene coma y punto, asumimos formato "1,500.50" (coma miles, punto decimal) 
        # o "1.500,50" (punto miles, coma decimal).
        # Vamos a remover el separador de miles y cambiar coma por punto decimal.
        
        # Determinar separador decimal y miles
        clean_num = number_str
        if ',' in clean_num and '.' in clean_num:
            if clean_num.rfind(',') > clean_num.rfind('.'):
                # ej. 1.000,50
                clean_num = clean_num.replace('.', '').replace(',', '.')
            else:
                # ej. 1,000.50
                clean_num = clean_num.replace(',', '')
        elif ',' in clean_num:
            # ej. 1000,50 o 1,000
            # Si hay 3 dígitos después de la coma (ej. 1,000), asumimos miles.
            parts = clean_num.split(',')
            if len(parts[-1]) == 3 and len(parts) == 2:
                clean_num = clean_num.replace(',', '')
            else:
                clean_num = clean_num.replace(',', '.')
                
        try:
            val = float(clean_num)
            unit_lower = unit.lower() if unit else None
            return (val, unit_lower)
        except ValueError:
            continue
            
    return None

