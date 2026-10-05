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

        # Extract items from multiline shredded table first
        raw_lines = [line.strip() for line in text.split('\n') if line.strip()]
        i = 0
        while i < len(raw_lines):
            if re.match(r'^\d+$', raw_lines[i]):
                item_no = raw_lines[i]
                if i + 1 < len(raw_lines) and re.match(r'^\d+(?:\.\d+)?$', raw_lines[i+1]):
                    qty = float(raw_lines[i+1])
                    unit = None
                    j_match = -1
                    # Search up to 25 lines ahead for the unit
                    for j in range(i + 2, min(i + 25, len(raw_lines))):
                        line_j = raw_lines[j]
                        
                        # Boundary protection: if we see two consecutive numbers, it's the start of the NEXT item
                        if j + 1 < len(raw_lines) and re.match(r'^\d+$', line_j) and re.match(r'^\d+(?:\.\d+)?$', raw_lines[j+1]):
                            break
                            
                        if re.match(r'^(UNIDAD|UNIDADES|KIT|KITS|CAJA|CAJAS|GLB|GLOBAL|SERVICIO|SERVICIOS|PAQUETE|PAQUETES|ROLLO|KG|GALON|GALONES|UND|UNDS|FRASCO|FRASCOS)$', line_j, re.IGNORECASE):
                            unit = line_j.upper()
                            j_match = j + 1
                            break

                    if unit:
                        desc_lines = raw_lines[i+2:j_match-1]
                        if desc_lines:
                            result.items.append(ProcurementItemCandidate(
                                item_number=item_no,
                                description=" ".join(desc_lines).strip(),
                                quantity=qty,
                                unit=unit,
                                source_document=source_document,
                                source_page=source_page,
                                source_fragment="\n".join(raw_lines[i:j_match]),
                                confidence=0.9
                            ))
                            i = j_match
                            continue
            i += 1

        # Check for item lines (Single-line table horizontal formats)
        unit_pattern = r'(UNIDAD|UNIDADES|KIT|KITS|CAJA|CAJAS|GLB|GLOBAL|SERVICIO|SERVICIOS|PAQUETE|PAQUETES|ROLLO|KG|GALON|GALONES|UND|UNDS)'
        item_regex_1 = re.compile(rf'(?:^|\s+)(\d+)\s+(.+?)\s+(\d+(?:\.\d+)?)\s+{unit_pattern}\b', re.IGNORECASE)
        item_regex_2 = re.compile(rf'(?:^|\s+)(\d+)\s+(\d+(?:\.\d+)?)\s+(.+?)\s+{unit_pattern}\b', re.IGNORECASE)

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
            # Find all matches in case paragraphs were joined
            matches_1 = list(item_regex_1.finditer(p))
            matches_2 = list(item_regex_2.finditer(p))
            all_matches = matches_1 + matches_2

            for item_match in all_matches:
                if item_match in matches_1:
                    qty = float(item_match.group(3))
                    desc = item_match.group(2).strip()
                    unit = item_match.group(4).upper()
                else:
                    qty = float(item_match.group(2))
                    desc = item_match.group(3).strip()
                    unit = item_match.group(4).upper()

                # Skip if already found in multiline to avoid duplicates
                if not any(it.item_number == item_match.group(1) for it in result.items):
                    active_item = ProcurementItemCandidate(
                        item_number=item_match.group(1),
                        description=desc,
                        quantity=qty,
                        unit=unit,
                        source_document=source_document,
                        source_page=source_page,
                        source_fragment=p,
                        confidence=0.9
                    )
                    result.items.append(active_item)
                else:
                    # Retrieve the already found active_item to attach specifications
                    active_item = next((it for it in result.items if it.item_number == item_match.group(1)), None)

            if all_matches:
                continue

            # If a multiline item matches the start of a paragraph, set it as active_item
            clean_for_multiline = p.split('\n')[0].strip()
            if re.match(r'^\d+$', clean_for_multiline):
                found_it = next((it for it in result.items if it.item_number == clean_for_multiline), None)
                if found_it:
                    active_item = found_it
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
