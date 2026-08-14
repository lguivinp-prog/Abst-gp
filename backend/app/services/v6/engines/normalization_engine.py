class NormalizationEngine:
    """
    Deterministic layer to normalize text into numeric values and standard units 
    before feeding into any AI or heuristic engines.
    """
    
    NUMBER_MAP = {
        "un": 1, "uno": 1, "dos": 2, "tres": 3, "cuatro": 4, "cinco": 5,
        "seis": 6, "siete": 7, "ocho": 8, "nueve": 9, "diez": 10,
        "once": 11, "doce": 12, "quince": 15, "veinte": 20, "treinta": 30
    }
    
    @classmethod
    def normalize_value(cls, raw_value: str) -> str:
        if not raw_value:
            return ""
            
        val_lower = raw_value.lower().strip()
        
        # Simple word replacement for numbers
        words = val_lower.split()
        normalized_words = []
        for w in words:
            if w in cls.NUMBER_MAP:
                normalized_words.append(str(cls.NUMBER_MAP[w]))
            else:
                normalized_words.append(w)
                
        # Future: handle date ranges, currencies normalization here
        
        return " ".join(normalized_words)
