import re
import unicodedata

def normalize_text_for_exact_match(text: str) -> str:
    """
    Normaliza el texto para validaciones exactas.
    - Convierte a minúsculas.
    - Reduce los saltos de línea y tabulaciones a espacios simples.
    - Elimina espacios al inicio y al final.
    - Conserva tildes, números, símbolos y signos de puntuación originales.
    """
    if not text:
        return ""
    
    # Reducir todos los espacios en blanco, tabulaciones y saltos a un solo espacio
    normalized = re.sub(r'\s+', ' ', text).strip()
    
    return normalized.lower()

def normalize_text_for_fuzzy_match(text: str) -> str:
    """
    Normaliza el texto agresivamente para algoritmos de similitud (Fuzzy Matching).
    - Aplica la normalización base (minúsculas, sin espacios múltiples).
    - Elimina las tildes (convierte á a a, ñ a n).
    - Elimina la puntuación no alfanumérica, excepto espacios (para no mezclar palabras).
    - Conserva siempre números y letras (alfanuméricos).
    """
    if not text:
        return ""
        
    exact_normalized = normalize_text_for_exact_match(text)
    
    # Remover tildes y acentos usando la forma NFKD de Unicode
    without_accents = unicodedata.normalize('NFKD', exact_normalized)\
                                 .encode('ASCII', 'ignore')\
                                 .decode('utf-8')
    
    # Dejar solo caracteres alfanuméricos y espacios en blanco
    # \w incluye [a-zA-Z0-9_]. También podemos ser más explícitos con a-z0-9\s
    fuzzy_normalized = re.sub(r'[^\w\s]', '', without_accents)
    
    # Volver a colapsar espacios por si se eliminó puntuación dejando espacios extra
    return re.sub(r'\s+', ' ', fuzzy_normalized).strip()
