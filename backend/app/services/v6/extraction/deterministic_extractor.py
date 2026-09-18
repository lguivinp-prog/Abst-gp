from typing import List
from .provider import (
    RequirementExtractionProvider,
    ExtractionResult,
    RequirementCandidate,
    ProcurementItemCandidate,
    ItemSpecificationCandidate
)
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

            is_kv = bool(re.match(r'^([A-ZÁÉÍÓÚÑa-záéíóúñ\s]+)\s*[:=]\s*(.+)$', line.strip()))

            # If it's a new list item, header, or KV pair, commit the previous paragraph
            if self._is_list_item(line) or is_header or line.startswith("PÃ¡g.") or is_kv:
                if current_paragraph:
                    paragraphs.append(" ".join(current_paragraph))
                    current_paragraph = []

            if is_header:
                paragraphs.append(line)
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
            r'^adquisicion de', r'^denominación de la',
            r'^especificaciones tecnicas para', r'^\d*\.?\s*entidad convocante',
            r'^pág\.', r'^firma del',
            r'^elaborado por',
            r'^finalidad p[úu]blica\b', r'^\d*\.?\s*objeto de la contrataci[óo]n\b'
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

    def extract(self, text: str, source_document: str, source_page: int = 1) -> ExtractionResult:
        result = ExtractionResult(requirements=[], items=[])

        # Phase 1 & 2: Reconstruct paragraphs
        paragraphs = self._reconstruct_paragraphs(text)

        # Check for item lines (e.g., "1 Tinta Negra 3 UNIDADES")
        item_regex = re.compile(r'^(\d+)\s+(.+?)\s+(\d+(?:\.\d+)?)\s+(UNIDAD|UNIDADES|KIT|KITS|CAJA|CAJAS|GLB|GLOBAL|SERVICIO|SERVICIOS|PAQUETE|PAQUETES|ROLLO|KG|GALON|GALONES)\b', re.IGNORECASE)

        # Custom Tabular Parser for Section 5.2 format
        active_item = None

        # State variables for template instruction block
        in_template_block = False

        for p in paragraphs:
            # Handle Template Instruction Blocks [...]
            if "[" in p and "]" not in p:
                in_template_block = True
                continue
            if in_template_block:
                if "]" in p:
                    in_template_block = False
                continue
            if "[" in p and "]" in p:
                continue

            # Check if paragraph is an item (Standard format)
            item_match = item_regex.search(p)
            if item_match:
                active_item = ProcurementItemCandidate(
                    item_number=item_match.group(1),
                    description=item_match.group(2).strip(),
                    quantity=float(item_match.group(3)),
                    unit=item_match.group(4).upper(),
                    source_document=source_document,
                    source_page=source_page,
                    source_fragment=p,
                    confidence=0.9
                )
                result.items.append(active_item)
                continue

            # Clean list item markers for the logic
            clean_p = re.sub(r'^(\d+[\.\)]|\-|\*|[a-zA-Z][\.\)])\s+', '', p).strip()

            # Phase 3: Noise Filtering
            if self._is_noise(clean_p):
                continue

            # Phase 4: Identify requirement
            text_lower = clean_p.lower()

            # Key-Value spec detection for active item
            kv_match = re.match(r'^([A-ZÁÉÍÓÚÑa-záéíóúñ\s]+)\s*[:=]\s*(.+)$', clean_p)
            if active_item and kv_match:
                key = kv_match.group(1).strip().upper()
                val = kv_match.group(2).strip()

                if key == "MODO DE USO":
                    result.requirements.append(
                        RequirementCandidate(
                            requirement_type="CONTEXT",
                            description=f"MODO DE USO: {val}",
                            value=None,
                            mandatory=False,
                            source_document=source_document,
                            source_page=source_page,
                            source_fragment=p,
                            confidence=0.9
                        )
                    )
                else:
                    # Specific exclusions like TEMPLATE INSTRUCTION can be handled here if needed
                    active_item.specifications.append(
                        ItemSpecificationCandidate(
                            name=key,
                            normalized_name=key.replace(' ', '_'),
                            value=val,
                            mandatory="True",
                            source_page=source_page,
                            confidence=0.9
                        )
                    )
                continue
            elif active_item and active_item.specifications and not self._is_requirement(clean_p) and not text_lower.startswith("finalidad"):
                # Multiline continuation for the last spec
                if "modo de uso" not in active_item.specifications[-1].name.lower():
                    last_spec = active_item.specifications[-1]
                    last_spec.value += " " + clean_p
                continue

            if "finalidad pública" in text_lower or "objeto de la contratación" in text_lower or "objetivo de la contratación" in text_lower:
                result.requirements.append(
                    RequirementCandidate(
                        requirement_type="CONTEXT",
                        description=clean_p,
                        value=None,
                        mandatory=True,
                        source_document=source_document,
                        source_page=source_page,
                        source_fragment=p,
                        confidence=1.0
                    )
                )
            elif self._is_requirement(clean_p) or self._is_requirement(p):
                result.requirements.append(
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

        return result
