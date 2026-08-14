import re

class PIIDetectionService:
    def __init__(self):
        self.patterns = [
            ("RUC", re.compile(r'\b(10|20)\d{9}\b')),
            ("DNI", re.compile(r'\b\d{8}\b'))
        ]
        
    def detect(self, text: str):
        matches = []
        for label, regex in self.patterns:
            for match in regex.finditer(text):
                matches.append({"start": match.start(), "end": match.end(), "label": label})
        return matches

pii_detector = PIIDetectionService()
