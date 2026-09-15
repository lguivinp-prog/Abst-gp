from typing import List
from .provider import RequirementExtractionProvider, RequirementCandidate
import re

class DeterministicRequirementExtractor(RequirementExtractionProvider):
    def _is_list_item(self, line: str) -> bool:
        return bool(re.match(r'^(\d+[\.\)]|\-|\*|[a-zA-Z][\.\)])\s+', line))

    def _ends_with_punctuation(self, line: str) -> bool:
        return line.endswith('.') or line.endswith(':') or line.endswith(';')

    def _reconstruct_paragraphs(self, text: str) -> List[str]:
        lines = [line.strip() for line in text.split('\n')]
        paragraphs = []
        current_paragraph = []

        for i, line in enumerate(lines):
            if not line:
                if current_paragraph:
                    paragraphs.append(" ".join(current_paragraph))
                    current_paragraph = []
                continue

            is_header = line.isupper() and len(line) < 60

            # If it's a new list item or header, commit the previous paragraph
            if self._is_list_item(line) or is_header or line.startswith("Pág."):
                if current_paragraph:
                    paragraphs.append(" ".join(current_paragraph))
                    current_paragraph = []

            if is_header:
                paragraphs.append(line)
                # Don't add to current_paragraph since it's already a paragraph
                continue

            current_paragraph.append(line)

            # If it ends with punctuation, commit the paragraph
            if self._ends_with_punctuation(line):
                paragraphs.append(" ".join(current_paragraph))
                current_paragraph = []

        if current_paragraph:
            paragraphs.append(" ".join(current_paragraph))

        return paragraphs

    def _is_noise(self, text: str) -> bool:
        # Regex for administrative noise
        noise_patterns = [
            r'^n° de pedido', r'^fecha\b', r'^direccion de', r'^organo y/o',
            r'^administracion de', r'^actividad operativa', r'^economicos y',
            r'^agraria amazonas', r'^meta presupuestaria', r'^descripción del ccmn',
            r'^adquisicion de', r'^denominación de la', r'^finalidad pública',
            r'^especificaciones tecnicas para', r'^\d+\.\s+entidad convocante',
            r'^\d+\.\s+objeto de la contratación', r'^pág\.', r'^firma del',
            r'^elaborado por'
        ]
        text_lower = text.lower()
        for pattern in noise_patterns:
            if re.search(pattern, text_lower):
                return True

        # Too short to be a requirement (unless it's an attribute like 'Voltaje: 220 V')
        if len(text) < 10 and ":" not in text:
            return True

        return False

    def _is_requirement(self, text: str) -> bool:
        text_lower = text.lower()

        # Action verbs
        if any(kw in text_lower for kw in ['debe', 'deberá', 'requiere', 'obligado', 'garantizar']):
            return True

        # Technical attributes or constraints
        if any(kw in text_lower for kw in ['mínimo', 'máximo', 'no menor', 'no mayor', 'capacidad', 'material', 'garantía', 'plazo']):
            return True

        # Technical key-value format (e.g. Diámetro: 50 mm)
        if re.search(r'^[a-záéíóúñ\s]+:\s*[\w\d\s]+$', text_lower, re.IGNORECASE) and len(text.split(':')) == 2:
            return True

        return False

    def extract(self, text: str, source_document: str, source_page: int = 1) -> List[RequirementCandidate]:
        candidates = []

        # Phase 1 & 2: Reconstruct paragraphs
        paragraphs = self._reconstruct_paragraphs(text)

        for p in paragraphs:
            # Clean list item markers for the logic
            clean_p = re.sub(r'^(\d+[\.\)]|\-|\*|[a-zA-Z][\.\)])\s+', '', p).strip()

            # Phase 3: Noise Filtering
            if self._is_noise(clean_p):
                continue

            # Phase 4: Identify requirement
            if self._is_requirement(clean_p) or self._is_requirement(p):
                candidates.append(
                    RequirementCandidate(
                        requirement_type="TECHNICAL",
                        description=clean_p,
                        value=None,
                        mandatory=True,
                        source_document=source_document,
                        source_page=source_page,
                        source_fragment=p,
                        confidence=0.8
                    )
                )

        return candidates
