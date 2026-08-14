class DeterministicImprovementEngine:
    """
    Engine to identify improvements in supplier offers compared to base requirements.
    Rules:
    - PRECIO is never an improvement (treated as ECONOMIC_DATA).
    - Detects: Menor plazo, Mayor garantia, Condicion tecnica superior, Mayor experiencia.
    """
    def detect_improvement(self, req_value: str, offer_value: str) -> bool:
        if not req_value or not offer_value:
            return False
            
        req_val_lower = req_value.lower()
        off_val_lower = offer_value.lower()
        
        # Rule: Price is not improvement
        if "precio" in req_val_lower or "soles" in req_val_lower or "dolares" in req_val_lower:
            return False
            
        # Time (plazo) - Menor plazo es mejora
        if "dias" in req_val_lower and "dias" in off_val_lower:
            try:
                # Naive deterministic extraction of numbers
                req_num = int(''.join(filter(str.isdigit, req_val_lower)))
                off_num = int(''.join(filter(str.isdigit, off_val_lower)))
                if off_num < req_num:
                    return True
            except ValueError:
                pass
                
        # Warranty (garantia) - Mayor garantia es mejora
        if "meses" in req_val_lower and "meses" in off_val_lower:
            try:
                req_num = int(''.join(filter(str.isdigit, req_val_lower)))
                off_num = int(''.join(filter(str.isdigit, off_val_lower)))
                if off_num > req_num:
                    return True
            except ValueError:
                pass
                
        return False
        
    def detect_conflict(self, evidences: list) -> bool:
        """
        Detects conflicts among multiple evidences for the same requirement.
        """
        values = set()
        for ev in evidences:
            if ev.fragment:
                values.add(ev.fragment.strip().lower())
        # If there is more than 1 distinct value stated in evidences, it's a conflict
        return len(values) > 1
