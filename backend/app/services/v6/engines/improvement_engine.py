import re
from typing import Optional, List, Dict, Any, Tuple

ATTRIBUTE_DEFINITIONS: Dict[str, Dict[str, Any]] = {
    "garantia": {
        "keywords": [
            r"\bgarant[ií]a(?:s)?\b",
            r"\bgarantizad[oa](?:s)?\b",
            r"\bgarantiz(?:ar|a|an|amos)?\b"
        ],
        "direction": "HIGHER_BETTER",
        "label": "garantía",
        "default_unit": "meses"
    },
    "soporte": {
        "keywords": [
            r"\bsoporte(?:\s+t[eé]cnico)?\b",
            r"\bmantenimiento(?:\s+preventivo|\s+correctivo)?\b",
            r"\basistencia(?:\s+t[eé]cnica)?\b",
            r"\bmesa\s+de\s+ayuda\b",
            r"\bhelpdesk\b",
            r"\bpostventa\b",
            r"\bpost-venta\b"
        ],
        "direction": "HIGHER_BETTER",
        "label": "soporte",
        "default_unit": "meses"
    },
    "entrega": {
        "keywords": [
            r"\bentrega(?:s)?\b",
            r"\bdespacho(?:s)?\b",
            r"\bsuministro(?:s)?\b",
            r"\benv[ií]o(?:s)?\b"
        ],
        "direction": "LOWER_BETTER",
        "label": "entrega",
        "default_unit": "dias"
    },
    "instalacion": {
        "keywords": [
            r"\binstalaci[oó]n(?:es)?\b",
            r"\bimplementaci[oó]n(?:es)?\b",
            r"\bpuesta\s+en\s+marcha\b",
            r"\bconfiguraci[oó]n(?:es)?\b"
        ],
        "direction": "LOWER_BETTER",
        "label": "instalación",
        "default_unit": "dias"
    },
    "experiencia": {
        "keywords": [
            r"\bexperiencia\b",
            r"\bfacturaci[oó]n\b"
        ],
        "direction": "HIGHER_BETTER",
        "label": "experiencia",
        "default_unit": "meses"
    },
    "plazo": {
        "keywords": [
            r"\bplazo(?:s)?\b",
            r"\bejecuci[oó]n\b",
            r"\bduraci[oó]n\b"
        ],
        "direction": "LOWER_BETTER",
        "label": "plazo general",
        "default_unit": "dias"
    }
}

WORD_NUMBERS: Dict[str, int] = {
    "un": 1, "uno": 1, "una": 1, "dos": 2, "tres": 3, "cuatro": 4, "cinco": 5,
    "seis": 6, "siete": 7, "ocho": 8, "nueve": 9, "diez": 10, "doce": 12,
    "quince": 15, "veinte": 20, "veinticuatro": 24, "treinta": 30,
    "treinta y seis": 36, "cuarenta y cinco": 45, "sesenta": 60, "noventa": 90
}

UNIT_PATTERN_STR = (
    r'(?:mes(?:es)?|a[ñn]o(?:s)?|semana(?:s)?|'
    r'd[ií]as?\s+(?:h[aá]biles?|utiles?|laborables?|laborales?)|'
    r'(?:h[aá]biles?|utiles?|laborables?|laborales?)\s+d[ií]as?|'
    r'd[ií]as?\s+(?:calendario|naturales?|consecutivos?|corridos?)|'
    r'(?:calendario|naturales?|consecutivos?|corridos?)\s+d[ií]as?|'
    r'd[ií]a(?:s)?)\b'
)

# Upper limit modifiers (cotas máximas / límites superiores)
UPPER_LIMIT_PATTERN = re.compile(
    r'\b(?:hasta|m[aá]xim[oa](?:\s+de)?|como\s+m[aá]ximo|tope(?:\s+de)?|'
    r'no\s+m[aá]s\s+de|no\s+mayor\s+a|no\s+superior\s+a|l[ií]mite(?:\s+m[aá]ximo)?(?:\s+de)?)\b',
    re.IGNORECASE
)

# Lower limit modifiers (cotas mínimas / pisos)
LOWER_LIMIT_PATTERN = re.compile(
    r'\b(?:m[ií]nim[oa](?:\s+de)?|como\s+m[ií]nimo|al\s+menos|'
    r'no\s+menos\s+de|no\s+menor\s+a|no\s+inferior\s+a|a\s+partir\s+de)\b',
    re.IGNORECASE
)

# Conservative negation patterns:
# Examples: "no incluye garantía", "sin garantía", "no ofrece", "no garantiza", "carece de soporte", "excluye instalación"
# NOTE: Must NOT match quantifiers such as "no menos de", "no menor a", "no más de", "no superior a"
NEGATION_PRECEDING_PATTERN = re.compile(
    r'\b(?:no\s+(?:se\s+)?(?:incluye|incluyen|contempla|contemplan|ofrece|ofrecen|otorga|otorgan|brinda|brindan|cubre|cubren|garantiza|garantizan|cuenta\s+con|tienen?)|'
    r'sin|excluye|excluyen|carece\s+de|no\s+aplica|cero|'
    r'no\s+(?!(?:menos|menor|m[aá]s|mayor|superior|inferior)\b))\b',
    re.IGNORECASE
)

# Trailing negations: "garantía no incluida", "soporte no disponible", "instalación no contemplada"
NEGATION_TRAILING_PATTERN = re.compile(
    r'\b(?:no\s+(?:incluid[oa]s?|contemplad[oa]s?|ofrecid[oa]s?|garantizad[oa]s?|disponibles?|aplicables?)|excluid[oa]s?|no\s+aplica)\b',
    re.IGNORECASE
)

DELIMITER_PATTERN = re.compile(
    r'[\.\;\n\r\t\|\/\•\–\—]|,\s*|\s+(?:y|e|pero|mientras\s+que|adem[aá]s|asimismo)\s+',
    re.IGNORECASE
)

# Range patterns: recognize expressions spanning bounds without discarding either extreme
RANGE_REPEATED = re.compile(
    rf'\b(?:de\s+)?(\d+)\s*({UNIT_PATTERN_STR})\s*(?:a|al|hasta|[-–—])\s*(\d+)\s*({UNIT_PATTERN_STR})',
    re.IGNORECASE
)
RANGE_ENTRE = re.compile(
    rf'\bentre\s+(\d+)\s+(?:y|e)\s+(\d+)\s*({UNIT_PATTERN_STR})',
    re.IGNORECASE
)
RANGE_HYPHEN_OR_A = re.compile(
    rf'\b(?:de\s+)?(\d+)\s*(?:a|al|hasta|[-–—])\s*(\d+)\s*({UNIT_PATTERN_STR})',
    re.IGNORECASE
)
SINGLE_METRIC = re.compile(
    rf'(\d+)\s*({UNIT_PATTERN_STR})',
    re.IGNORECASE
)

words_sorted = sorted(WORD_NUMBERS.keys(), key=lambda x: -len(x))
words_pattern = r'(?:' + '|'.join(re.escape(w) for w in words_sorted) + r')'

RANGE_WORDS_ENTRE = re.compile(
    rf'\bentre\s+({words_pattern})\s+(?:y|e)\s+({words_pattern})\s*({UNIT_PATTERN_STR})',
    re.IGNORECASE
)
RANGE_WORDS = re.compile(
    rf'\b(?:de\s+)?({words_pattern})\s*(?:a|al|hasta|[-–—])\s*({words_pattern})\s*({UNIT_PATTERN_STR})',
    re.IGNORECASE
)
SINGLE_WORD_METRIC = re.compile(
    rf'\b({words_pattern})\s*({UNIT_PATTERN_STR})',
    re.IGNORECASE
)


def _parse_unit_and_val(num: int, unit_str: str) -> Tuple[int, str]:
    u = unit_str.lower()
    if "mes" in u:
        return num, "meses"
    elif "año" in u or "ano" in u:
        return num * 12, "meses"
    elif "sem" in u:
        return num * 7, "dias"
    elif any(k in u for k in ["habil", "hábil", "util", "útil", "laborab", "laboral"]):
        return num, "dias_habiles"
    elif any(k in u for k in ["calendario", "natural", "consecutiv", "corrido"]):
        return num, "dias_calendario"
    else:
        return num, "dias"


def _format_unit(unit: Optional[str]) -> str:
    if not unit:
        return ""
    if unit == "dias_habiles":
        return "días hábiles"
    if unit == "dias_calendario":
        return "días calendario"
    if unit == "dias":
        return "días"
    return unit


class AttributeObservation:
    def __init__(
        self,
        attribute: str,
        value: Optional[int] = None,
        unit: Optional[str] = None,
        is_negated: bool = False,
        is_ambiguous: bool = False,
        raw_text: str = "",
        is_range: bool = False,
        range_min: Optional[int] = None,
        range_max: Optional[int] = None,
        limit_modifier: Optional[str] = None
    ):
        self.attribute = attribute
        self.value = value
        self.unit = unit
        self.is_negated = is_negated
        self.is_ambiguous = is_ambiguous
        self.raw_text = raw_text
        self.is_range = is_range
        self.range_min = range_min
        self.range_max = range_max
        self.limit_modifier = limit_modifier

    def __repr__(self):
        return (
            f"AttributeObservation({self.attribute}, val={self.value} {self.unit}, "
            f"neg={self.is_negated}, amb={self.is_ambiguous}, "
            f"range={self.is_range}({self.range_min}-{self.range_max}), limit={self.limit_modifier})"
        )


class DeterministicImprovementEngine:
    """
    Engine to identify improvements in supplier offers compared to base requirements
    and evaluate technical compliance between requirements and verified documentary evidence.
    Rules:
    - PRECIO is never an improvement (treated as ECONOMIC_DATA).
    - Attributes are explicitly tied to specific conditions: garantía, soporte, entrega, instalación.
    - Does not conflate deadlines of different prestations (e.g. entrega vs instalación, garantía vs soporte).
    - Conservative negation detection: explicit negation leads to FAILED; ambiguous negation leads to REQUIERE_REVISION.
    - OCR-resilient span partitioning: unpunctuated multi-attribute text is scoped cleanly.
    - Multi-attribute conflation avoidance: a single metric is not applied indiscriminately to multiple attributes.
    - Recognizes ranges, limits, and modalities of temporal computation:
        * No range value or upper limit can automatically become compliance or improvement.
        * Neither end of a range is discarded for lacking a repeated unit.
        * Días hábiles and días calendario are not equated without an accredited conversion rule.
    - Deterministic fail-closed architecture: no AI heuristics or unverified assumptions.
    """

    @classmethod
    def extract_observations(cls, text: str) -> List[AttributeObservation]:
        """
        Extracts structured observations of technical attributes, their metrics, negations,
        ranges, upper/lower limits, and temporal modalities from text.
        """
        if not text:
            return []

        # 1. Attribute spans
        raw_attrs = []
        for attr_name, attr_info in ATTRIBUTE_DEFINITIONS.items():
            for kw in attr_info["keywords"]:
                for m in re.finditer(kw, text, re.IGNORECASE):
                    raw_attrs.append((m.start(), m.end(), attr_name, m.group(0)))

        # Remove overlaps
        raw_attrs.sort(key=lambda x: (x[0], -x[1]))
        filtered_attrs = []
        for a in raw_attrs:
            overlap = False
            for fa in filtered_attrs:
                if not (a[1] <= fa[0] or a[0] >= fa[1]):
                    overlap = True
                    break
            if not overlap:
                filtered_attrs.append(a)

        # Subsume generic "plazo" if adjacent/near a specific attribute (e.g. "plazo de entrega")
        final_attrs = []
        for a in filtered_attrs:
            if a[2] == "plazo":
                is_subsumed = False
                for other in filtered_attrs:
                    if other[2] != "plazo" and abs(a[0] - other[0]) < 25:
                        is_subsumed = True
                        break
                if is_subsumed:
                    continue
            final_attrs.append(a)
        final_attrs.sort(key=lambda x: x[0])

        # 2. Metric and range spans
        raw_metrics = []

        # 1. Repeated unit range: e.g. "de 12 meses a 36 meses", "12 meses a 36 meses"
        for m in RANGE_REPEATED.finditer(text):
            n1, u1 = _parse_unit_and_val(int(m.group(1)), m.group(2))
            n2, u2 = _parse_unit_and_val(int(m.group(3)), m.group(4))
            raw_metrics.append((m.start(), m.end(), n2, u2, m.group(0), True, min(n1, n2), max(n1, n2), None))

        # 2. 'entre X y Y unit': e.g. "entre 12 y 36 meses"
        for m in RANGE_ENTRE.finditer(text):
            if not any(not (m.end() <= rm[0] or m.start() >= rm[1]) for rm in raw_metrics):
                n1, u = _parse_unit_and_val(int(m.group(1)), m.group(3))
                n2, u = _parse_unit_and_val(int(m.group(2)), m.group(3))
                raw_metrics.append((m.start(), m.end(), n2, u, m.group(0), True, min(n1, n2), max(n1, n2), None))

        # 3. 'X a/al/hasta/- Y unit': e.g. "12 a 36 meses", "12-36 meses", "10 a 20 días hábiles"
        for m in RANGE_HYPHEN_OR_A.finditer(text):
            if not any(not (m.end() <= rm[0] or m.start() >= rm[1]) for rm in raw_metrics):
                n1, u = _parse_unit_and_val(int(m.group(1)), m.group(3))
                n2, u = _parse_unit_and_val(int(m.group(2)), m.group(3))
                raw_metrics.append((m.start(), m.end(), n2, u, m.group(0), True, min(n1, n2), max(n1, n2), None))

        # 4. Word number ranges: e.g. "entre diez y veinte días", "de doce a treinta y seis meses"
        for m in RANGE_WORDS_ENTRE.finditer(text):
            if not any(not (m.end() <= rm[0] or m.start() >= rm[1]) for rm in raw_metrics):
                w1 = m.group(1).lower()
                w2 = m.group(2).lower()
                if w1 in WORD_NUMBERS and w2 in WORD_NUMBERS:
                    n1, u = _parse_unit_and_val(WORD_NUMBERS[w1], m.group(3))
                    n2, u = _parse_unit_and_val(WORD_NUMBERS[w2], m.group(3))
                    raw_metrics.append((m.start(), m.end(), n2, u, m.group(0), True, min(n1, n2), max(n1, n2), None))

        for m in RANGE_WORDS.finditer(text):
            if not any(not (m.end() <= rm[0] or m.start() >= rm[1]) for rm in raw_metrics):
                w1 = m.group(1).lower()
                w2 = m.group(2).lower()
                if w1 in WORD_NUMBERS and w2 in WORD_NUMBERS:
                    n1, u = _parse_unit_and_val(WORD_NUMBERS[w1], m.group(3))
                    n2, u = _parse_unit_and_val(WORD_NUMBERS[w2], m.group(3))
                    raw_metrics.append((m.start(), m.end(), n2, u, m.group(0), True, min(n1, n2), max(n1, n2), None))

        # 5. Single digits + unit
        for m in SINGLE_METRIC.finditer(text):
            if any(not (m.end() <= rm[0] or m.start() >= rm[1]) for rm in raw_metrics):
                continue
            num, unit = _parse_unit_and_val(int(m.group(1)), m.group(2))
            pre_text = text[max(0, m.start() - 35):m.start()]
            post_text = text[m.end():min(len(text), m.end() + 25)]
            limit_mod = None
            if UPPER_LIMIT_PATTERN.search(pre_text) or UPPER_LIMIT_PATTERN.search(post_text):
                limit_mod = "UPPER"
            elif LOWER_LIMIT_PATTERN.search(pre_text) or LOWER_LIMIT_PATTERN.search(post_text):
                limit_mod = "LOWER"
            raw_metrics.append((m.start(), m.end(), num, unit, m.group(0), False, None, None, limit_mod))

        # 6. Single word numbers + unit
        for word, val in sorted(WORD_NUMBERS.items(), key=lambda x: -len(x[0])):
            pattern = rf'\b{word}\s*({UNIT_PATTERN_STR})'
            for m in re.finditer(pattern, text, re.IGNORECASE):
                if any(not (m.end() <= rm[0] or m.start() >= rm[1]) for rm in raw_metrics):
                    continue
                num, unit = _parse_unit_and_val(val, m.group(1))
                pre_text = text[max(0, m.start() - 35):m.start()]
                post_text = text[m.end():min(len(text), m.end() + 25)]
                limit_mod = None
                if UPPER_LIMIT_PATTERN.search(pre_text) or UPPER_LIMIT_PATTERN.search(post_text):
                    limit_mod = "UPPER"
                elif LOWER_LIMIT_PATTERN.search(pre_text) or LOWER_LIMIT_PATTERN.search(post_text):
                    limit_mod = "LOWER"
                raw_metrics.append((m.start(), m.end(), num, unit, m.group(0), False, None, None, limit_mod))

        raw_metrics.sort(key=lambda x: x[0])

        # 3. Delimiters
        delimiters = [m.start() for m in DELIMITER_PATTERN.finditer(text)]

        if not final_attrs:
            obs_list = []
            for rm in raw_metrics:
                is_ambig = rm[5] or (rm[8] == "UPPER")
                obs_list.append(AttributeObservation(
                    attribute="_unattributed",
                    value=rm[2],
                    unit=rm[3],
                    raw_text=rm[4],
                    is_range=rm[5],
                    range_min=rm[6],
                    range_max=rm[7],
                    limit_modifier=rm[8],
                    is_ambiguous=is_ambig
                ))
            return obs_list

        # 4. Scope boundaries (explicit delimiters + unpunctuated transition points)
        boundaries = sorted(list(set([0, len(text)] + delimiters)))

        for i in range(len(final_attrs) - 1):
            a1 = final_attrs[i]
            a2 = final_attrs[i + 1]
            has_delim = any(a1[1] <= d <= a2[0] for d in delimiters)
            if not has_delim:
                # If a metric sits between a1 and a2, boundary exists before a2
                m_between = [m for m in raw_metrics if a1[0] <= m[0] <= a2[0] or (m[0] <= a1[0] and a1[1] <= a2[0])]
                if m_between:
                    boundaries.append(a2[0])

        boundaries = sorted(list(set(boundaries)))

        chunks = []
        for i in range(len(boundaries) - 1):
            b_start = boundaries[i]
            b_end = boundaries[i + 1]
            chunk_str = text[b_start:b_end].strip()
            if chunk_str:
                chunks.append((b_start, b_end, chunk_str))

        observations: List[AttributeObservation] = []

        for c_start, c_end, c_text in chunks:
            c_attrs = [a for a in final_attrs if c_start <= a[0] < c_end]
            c_metrics = [m for m in raw_metrics if c_start <= m[0] < c_end]

            neg_prec = bool(NEGATION_PRECEDING_PATTERN.search(c_text))
            neg_trail = bool(NEGATION_TRAILING_PATTERN.search(c_text))
            is_negated = neg_prec or neg_trail

            if not c_attrs and not c_metrics:
                continue

            if c_attrs and not c_metrics:
                for a in c_attrs:
                    observations.append(AttributeObservation(
                        attribute=a[2],
                        value=None,
                        unit=None,
                        is_negated=is_negated,
                        is_ambiguous=False,
                        raw_text=c_text
                    ))
            elif not c_attrs and c_metrics:
                for m in c_metrics:
                    is_ambig = m[5] or (m[8] == "UPPER") or True
                    observations.append(AttributeObservation(
                        attribute="_unattributed",
                        value=m[2],
                        unit=m[3],
                        is_negated=is_negated,
                        is_ambiguous=True,
                        raw_text=c_text,
                        is_range=m[5],
                        range_min=m[6],
                        range_max=m[7],
                        limit_modifier=m[8]
                    ))
            elif len(c_attrs) == 1 and len(c_metrics) == 1:
                a = c_attrs[0]
                m = c_metrics[0]
                direction = ATTRIBUTE_DEFINITIONS.get(a[2], {}).get("direction", "HIGHER_BETTER")
                limit_mod = m[8]
                if not limit_mod:
                    if UPPER_LIMIT_PATTERN.search(c_text):
                        limit_mod = "UPPER"
                    elif LOWER_LIMIT_PATTERN.search(c_text):
                        limit_mod = "LOWER"
                is_ambig = m[5] or (limit_mod == "UPPER" and direction == "HIGHER_BETTER")
                observations.append(AttributeObservation(
                    attribute=a[2],
                    value=m[2],
                    unit=m[3],
                    is_negated=is_negated,
                    is_ambiguous=is_ambig,
                    raw_text=c_text,
                    is_range=m[5],
                    range_min=m[6],
                    range_max=m[7],
                    limit_modifier=limit_mod
                ))
            elif len(c_attrs) > 1 and len(c_metrics) == 1:
                # Rule 3: Multiple attributes sharing a single metric within a clause => ambiguous
                for a in c_attrs:
                    observations.append(AttributeObservation(
                        attribute=a[2],
                        value=c_metrics[0][2],
                        unit=c_metrics[0][3],
                        is_negated=is_negated,
                        is_ambiguous=True,
                        raw_text=c_text,
                        is_range=c_metrics[0][5],
                        range_min=c_metrics[0][6],
                        range_max=c_metrics[0][7],
                        limit_modifier=c_metrics[0][8]
                    ))
            elif len(c_attrs) == 1 and len(c_metrics) > 1:
                distinct_metrics = set((m[2], m[3]) for m in c_metrics)
                if len(distinct_metrics) == 1:
                    # Identical repeated metric (e.g. description + value redundancy: "36 meses 36 meses")
                    m = c_metrics[0]
                    direction = ATTRIBUTE_DEFINITIONS.get(c_attrs[0][2], {}).get("direction", "HIGHER_BETTER")
                    limit_mod = m[8]
                    is_ambig = m[5] or (limit_mod == "UPPER" and direction == "HIGHER_BETTER")
                    observations.append(AttributeObservation(
                        attribute=c_attrs[0][2],
                        value=m[2],
                        unit=m[3],
                        is_negated=is_negated,
                        is_ambiguous=is_ambig,
                        raw_text=c_text,
                        is_range=m[5],
                        range_min=m[6],
                        range_max=m[7],
                        limit_modifier=limit_mod
                    ))
                else:
                    # Genuinely conflicting multiple numbers for single attribute
                    for m in c_metrics:
                        observations.append(AttributeObservation(
                            attribute=c_attrs[0][2],
                            value=m[2],
                            unit=m[3],
                            is_negated=is_negated,
                            is_ambiguous=True,
                            raw_text=c_text,
                            is_range=m[5],
                            range_min=m[6],
                            range_max=m[7],
                            limit_modifier=m[8]
                        ))
            else:
                c_items = []
                for a in c_attrs:
                    c_items.append(('attr', a[0], a))
                for m in c_metrics:
                    c_items.append(('metric', m[0], m))
                c_items.sort(key=lambda x: x[1])

                types = [x[0] for x in c_items]
                if types == ['attr', 'metric'] * (len(c_items) // 2):
                    for i in range(0, len(c_items), 2):
                        a = c_items[i][2]
                        m = c_items[i + 1][2]
                        slice_text = text[a[0]:m[1]]
                        loc_neg = bool(NEGATION_PRECEDING_PATTERN.search(slice_text)) or bool(NEGATION_TRAILING_PATTERN.search(slice_text))
                        direction = ATTRIBUTE_DEFINITIONS.get(a[2], {}).get("direction", "HIGHER_BETTER")
                        limit_mod = m[8]
                        if not limit_mod:
                            if UPPER_LIMIT_PATTERN.search(slice_text):
                                limit_mod = "UPPER"
                            elif LOWER_LIMIT_PATTERN.search(slice_text):
                                limit_mod = "LOWER"
                        is_ambig = m[5] or (limit_mod == "UPPER" and direction == "HIGHER_BETTER")
                        observations.append(AttributeObservation(
                            attribute=a[2],
                            value=m[2],
                            unit=m[3],
                            is_negated=loc_neg or is_negated,
                            is_ambiguous=is_ambig,
                            raw_text=slice_text,
                            is_range=m[5],
                            range_min=m[6],
                            range_max=m[7],
                            limit_modifier=limit_mod
                        ))
                elif types == ['metric', 'attr'] * (len(c_items) // 2):
                    for i in range(0, len(c_items), 2):
                        m = c_items[i][2]
                        a = c_items[i + 1][2]
                        slice_text = text[m[0]:a[1]]
                        loc_neg = bool(NEGATION_PRECEDING_PATTERN.search(slice_text)) or bool(NEGATION_TRAILING_PATTERN.search(slice_text))
                        direction = ATTRIBUTE_DEFINITIONS.get(a[2], {}).get("direction", "HIGHER_BETTER")
                        limit_mod = m[8]
                        if not limit_mod:
                            if UPPER_LIMIT_PATTERN.search(slice_text):
                                limit_mod = "UPPER"
                            elif LOWER_LIMIT_PATTERN.search(slice_text):
                                limit_mod = "LOWER"
                        is_ambig = m[5] or (limit_mod == "UPPER" and direction == "HIGHER_BETTER")
                        observations.append(AttributeObservation(
                            attribute=a[2],
                            value=m[2],
                            unit=m[3],
                            is_negated=loc_neg or is_negated,
                            is_ambiguous=is_ambig,
                            raw_text=slice_text,
                            is_range=m[5],
                            range_min=m[6],
                            range_max=m[7],
                            limit_modifier=limit_mod
                        ))
                else:
                    for a in c_attrs:
                        observations.append(AttributeObservation(
                            attribute=a[2],
                            value=None,
                            unit=None,
                            is_negated=is_negated,
                            is_ambiguous=True,
                            raw_text=c_text
                        ))

        return observations

    @classmethod
    def extract_attribute_metrics(cls, text: str) -> Dict[str, List[Tuple[int, str]]]:
        """
        Backward-compatible dictionary mapping: attribute -> list of (value, unit).
        Only includes non-ambiguous, non-negated metrics, excluding ranges and upper limits.
        """
        obs_list = cls.extract_observations(text)
        res: Dict[str, List[Tuple[int, str]]] = {}
        for obs in obs_list:
            if (
                not obs.is_negated
                and not obs.is_ambiguous
                and not obs.is_range
                and obs.limit_modifier != "UPPER"
                and obs.value is not None
                and obs.unit
            ):
                res.setdefault(obs.attribute, []).append((obs.value, obs.unit))
        return res

    @staticmethod
    def _extract_months(text: str) -> Optional[int]:
        if not text:
            return None
        match = re.search(r'(\d+)\s*(?:mes|meses)\b', text, re.IGNORECASE)
        if match:
            try:
                return int(match.group(1))
            except ValueError:
                pass
        return None

    @staticmethod
    def _extract_days(text: str) -> Optional[int]:
        if not text:
            return None
        match = re.search(r'(\d+)\s*(?:d[ií]a|d[ií]as)\b', text, re.IGNORECASE)
        if match:
            try:
                return int(match.group(1))
            except ValueError:
                pass
        return None

    def detect_improvement(self, req_value: str, offer_value: str) -> bool:
        """
        Detects whether an offer improves upon the requirement.
        Rules:
        - Price is never an improvement.
        - Ranges, upper limit modifiers, or ambiguous observations cannot be declared improvement.
        - Non-equivalent temporal modalities (días hábiles vs días calendario) cannot be declared improvement.
        """
        if not req_value or not offer_value:
            return False

        req_val_lower = req_value.lower()
        off_val_lower = offer_value.lower()

        # Rule: Price is not improvement
        if "precio" in req_val_lower or "soles" in req_val_lower or "dolares" in req_val_lower or "monto" in req_val_lower:
            return False

        req_obs = self.extract_observations(req_value)
        off_obs = self.extract_observations(offer_value)

        # Fail-closed: ranges, upper limits in offer, or ambiguous observations cannot be improvement
        if any(o.is_range or o.is_ambiguous for o in req_obs + off_obs):
            return False
        if any(o.limit_modifier == "UPPER" for o in off_obs):
            return False

        # Attribute-aware comparison
        req_attrs = self.extract_attribute_metrics(req_value)
        off_attrs = self.extract_attribute_metrics(offer_value)

        # If attributes are detected on both sides, check for improvement on matching attributes
        common_attrs = set(req_attrs.keys()).intersection(set(off_attrs.keys())) - {"_unattributed"}
        if common_attrs:
            any_improved = False
            for attr in common_attrs:
                direction = ATTRIBUTE_DEFINITIONS[attr]["direction"]
                req_val, req_unit = req_attrs[attr][0]
                off_val, off_unit = off_attrs[attr][0]
                # Unit and temporal modality compatibility check:
                if req_unit != off_unit:
                    return False
                if direction == "HIGHER_BETTER" and off_val > req_val:
                    any_improved = True
                elif direction == "LOWER_BETTER" and off_val < req_val:
                    any_improved = True
                elif direction == "HIGHER_BETTER" and off_val < req_val:
                    return False
                elif direction == "LOWER_BETTER" and off_val > req_val:
                    return False
            return any_improved

        # Fallback for simple short phrases (backward compatibility)
        # Check raw text for range indicators, upper limits, or mixed modalities
        if RANGE_HYPHEN_OR_A.search(req_value) or RANGE_HYPHEN_OR_A.search(offer_value):
            return False
        if RANGE_ENTRE.search(req_value) or RANGE_ENTRE.search(offer_value):
            return False
        if RANGE_REPEATED.search(req_value) or RANGE_REPEATED.search(offer_value):
            return False
        if UPPER_LIMIT_PATTERN.search(offer_value):
            return False

        # Check temporal modality mismatch in fallback
        req_has_habiles = bool(re.search(r'\b(?:h[aá]biles?|utiles?|laborables?|laborales?)\b', req_val_lower))
        off_has_habiles = bool(re.search(r'\b(?:h[aá]biles?|utiles?|laborables?|laborales?)\b', off_val_lower))
        req_has_calendario = bool(re.search(r'\b(?:calendario|naturales?|consecutivos?|corridos?)\b', req_val_lower))
        off_has_calendario = bool(re.search(r'\b(?:calendario|naturales?|consecutivos?|corridos?)\b', off_val_lower))
        if req_has_habiles != off_has_habiles or req_has_calendario != off_has_calendario:
            return False

        req_days = self._extract_days(req_val_lower)
        off_days = self._extract_days(off_val_lower)
        if req_days is not None and off_days is not None:
            if off_days < req_days:
                return True

        req_months = self._extract_months(req_val_lower)
        off_months = self._extract_months(off_val_lower)
        if req_months is not None and off_months is not None:
            if off_months > req_months:
                return True

        return False

    def detect_conflict(self, evidences: list) -> bool:
        """
        Detects conflicting claims among multiple evidences for the same requirement.
        Identifies contradictions when multiple evidences assert different quantitative
        values for the same technical attribute, indeterminate ranges, or when positive
        affirmations and negations collide.
        """
        attr_values: Dict[str, set] = {}
        attr_has_positive: Dict[str, bool] = {}
        attr_has_negation: Dict[str, bool] = {}
        unattributed_values = set()

        for ev in evidences:
            frag = getattr(ev, "fragment", None)
            if not frag or not frag.strip():
                continue
            obs_list = self.extract_observations(frag)
            if not obs_list:
                continue
            for obs in obs_list:
                if obs.attribute == "_unattributed":
                    if obs.value is not None:
                        unattributed_values.add((obs.value, obs.unit))
                else:
                    if obs.is_negated:
                        attr_has_negation[obs.attribute] = True
                    else:
                        attr_has_positive[obs.attribute] = True
                        if obs.value is not None:
                            attr_values.setdefault(obs.attribute, set()).add(obs.value)

        for attr_name, vals in attr_values.items():
            if len(vals) > 1:
                return True
            if attr_has_positive.get(attr_name) and attr_has_negation.get(attr_name):
                return True

        for attr_name in set(attr_has_positive.keys()).intersection(set(attr_has_negation.keys())):
            return True

        unit_vals: Dict[str, set] = {}
        for val, unit in unattributed_values:
            unit_vals.setdefault(unit, set()).add(val)
        for unit, vals in unit_vals.items():
            if len(vals) > 1:
                return True

        return False

    def contrast_technical_compliance(
        self,
        req_desc: str,
        req_value: Optional[str],
        fragments: List[str]
    ) -> Dict[str, Any]:
        """
        Contrasts verified evidence fragments against requirement criteria.
        Extracts attribute-bound metrics, evaluates explicit negations, limits, ranges,
        temporal modalities, and applies conservative fail-closed deterministic comparison.
        Returns a dict with keys: 'status', 'explanation', 'confidence'.
        """
        if req_desc and req_value:
            if req_value.strip().lower() in req_desc.lower():
                combined_req = req_desc.strip()
            else:
                combined_req = f"{req_desc} {req_value}".strip()
        else:
            combined_req = f"{req_desc or ''} {req_value or ''}".strip()

        combined_frag = " ".join(f for f in fragments if f).strip()

        if not combined_frag:
            return {
                "status": "MISSING_DATA",
                "explanation": "No se cuenta con texto de evidencia para contrastar",
                "confidence": 0.0
            }

        req_obs = self.extract_observations(combined_req)

        off_obs: List[AttributeObservation] = []
        for frag in fragments:
            if frag and frag.strip():
                off_obs.extend(self.extract_observations(frag))

        if not req_obs or all(o.attribute == "_unattributed" for o in req_obs):
            return {
                "status": "REQUIERE_REVISION",
                "explanation": "Evidencia documental verificada; pendiente de revisión técnica humana para determinar cumplimiento frente al requisito.",
                "confidence": 0.5
            }

        req_map: Dict[str, List[AttributeObservation]] = {}
        for o in req_obs:
            req_map.setdefault(o.attribute, []).append(o)

        off_map: Dict[str, List[AttributeObservation]] = {}
        for o in off_obs:
            off_map.setdefault(o.attribute, []).append(o)

        failed_details: List[str] = []
        improvement_details: List[str] = []
        passed_details: List[str] = []
        ambiguous_details: List[str] = []

        for attr_name, req_list in req_map.items():
            if attr_name == "_unattributed":
                ambiguous_details.append("Requisito contiene métricas con atributo no identificado inequívocamente")
                continue

            attr_info = ATTRIBUTE_DEFINITIONS.get(attr_name, {
                "direction": "HIGHER_BETTER",
                "label": attr_name,
                "default_unit": "meses"
            })
            attr_label = attr_info["label"]
            direction = attr_info["direction"]

            # Check for range in requirement itself
            if any(o.is_range for o in req_list):
                r_obs = [o for o in req_list if o.is_range][0]
                ambiguous_details.append(
                    f"Requisito contiene un rango condicional para {attr_label} ({r_obs.range_min}-{r_obs.range_max} {_format_unit(r_obs.unit)})"
                )
                continue

            # Check for ambiguity in requirement itself
            if any(o.is_ambiguous for o in req_list):
                ambiguous_details.append(f"Requisito contiene formulación ambigua para {attr_label}")
                continue

            req_distinct_vals = set(o.value for o in req_list if o.value is not None)
            if len(req_distinct_vals) > 1:
                ambiguous_details.append(f"Requisito contiene valores divergentes para {attr_label}: {req_distinct_vals}")
                continue

            req_val = req_list[0].value
            req_unit = req_list[0].unit

            # Find matching in offer
            off_list = off_map.get(attr_name)
            if not off_list:
                # Permitted single-deadline correspondence: generic 'plazo' and specific 'entrega'
                # when no competing prestation exists on either side
                if attr_name == "plazo" and "entrega" in off_map and "instalacion" not in off_map and "instalacion" not in req_map:
                    off_list = off_map["entrega"]
                elif attr_name == "entrega" and "plazo" in off_map and "instalacion" not in off_map and "instalacion" not in req_map:
                    off_list = off_map["plazo"]

            if not off_list:
                if "_unattributed" in off_map and off_map["_unattributed"]:
                    ambiguous_details.append(
                        f"No se pudo determinar inequívocamente la correspondencia del atributo {attr_label} en la evidencia documental (métricas sin atributo identificado)"
                    )
                else:
                    ambiguous_details.append(
                        f"Evidencia documental no contiene acreditación para el atributo requerido: {attr_label}"
                    )
                continue

            # Check for explicit negation in offer for this required attribute
            negated_obs = [o for o in off_list if o.is_negated]
            if negated_obs:
                failed_details.append(
                    f"Incumplimiento técnico: la evidencia indica expresamente la negación o exclusión del atributo requerido: {attr_label} («{negated_obs[0].raw_text}»)"
                )
                continue

            # Check for range in offer (Rule: no range can automatically convert to compliance or improvement)
            if any(o.is_range for o in off_list):
                range_obs = [o for o in off_list if o.is_range][0]
                r_disp = f"{range_obs.range_min}-{range_obs.range_max} {_format_unit(range_obs.unit)}"
                ambiguous_details.append(
                    f"Evidencia documental contiene un rango condicional o indeterminado para {attr_label} ({r_disp}) frente al requisito estricto"
                )
                continue

            # Check for upper limit modifier in offer (Rule: upper limits on higher_better do not guarantee minimum)
            if any(o.limit_modifier == "UPPER" for o in off_list):
                u_obs = [o for o in off_list if o.limit_modifier == "UPPER"][0]
                if direction == "HIGHER_BETTER":
                    ambiguous_details.append(
                        f"Evidencia documental expresa una cota máxima o límite superior para {attr_label} («{u_obs.raw_text}») que no garantiza el cumplimiento inequívoco del mínimo requerido"
                    )
                else:
                    ambiguous_details.append(
                        f"Evidencia documental expresa un límite superior o cota condicional para {attr_label} («{u_obs.raw_text}») que requiere validación técnica sobre el plazo certero"
                    )
                continue

            # Check if offer is ambiguous for this attribute
            if any(o.is_ambiguous for o in off_list):
                ambiguous_details.append(
                    f"Ambigüedad técnica en la evidencia documental: asociación no inequívoca para {attr_label}"
                )
                continue

            off_distinct_vals = set(o.value for o in off_list if o.value is not None)
            if len(off_distinct_vals) > 1:
                vals_str = " vs ".join(f"{v} {_format_unit(off_list[0].unit)}" for v in sorted(off_distinct_vals))
                ambiguous_details.append(
                    f"Ambigüedad o contradicción técnica: la evidencia contiene valores contradictorios para {attr_label} ({vals_str})"
                )
                continue

            if not off_distinct_vals or None in [o.value for o in off_list]:
                ambiguous_details.append(
                    f"Evidencia documental menciona {attr_label} pero no precisa una cantidad métrica verificable"
                )
                continue

            off_val = off_list[0].value
            off_unit = off_list[0].unit

            if req_val is None:
                ambiguous_details.append(f"Requisito menciona {attr_label} sin métrica cuantitativa explícita")
                continue

            # Unit and temporal modality compatibility check:
            if req_unit != off_unit:
                req_u_disp = _format_unit(req_unit)
                off_u_disp = _format_unit(off_unit)
                if "dias" in (req_unit or "") and "dias" in (off_unit or ""):
                    ambiguous_details.append(
                        f"Discrepancia de base temporal para {attr_label}: cómputo en {off_u_disp} frente a {req_u_disp} sin regla de conversión acreditada"
                    )
                else:
                    ambiguous_details.append(
                        f"Discrepancia de unidades para {attr_label}: requerido en {req_u_disp}, ofrecido en {off_u_disp}"
                    )
                continue

            req_u_disp = _format_unit(req_unit)
            off_u_disp = _format_unit(off_unit)

            # Deterministic comparison
            if direction == "HIGHER_BETTER":
                if off_val < req_val:
                    failed_details.append(
                        f"Incumplimiento técnico: {attr_label} ofrecido/a de {off_val} {off_u_disp} no alcanza el mínimo requerido de {req_val} {req_u_disp}"
                    )
                elif off_val > req_val:
                    improvement_details.append(
                        f"Mejora técnica acreditada y validada documentalmente: {attr_label} ofrecido/a de {off_val} {off_u_disp} supera el mínimo requerido de {req_val} {req_u_disp}"
                    )
                else:
                    passed_details.append(
                        f"Cumplimiento técnico acreditado y validado documentalmente: {attr_label} de {off_val} {off_u_disp} cumple el requisito de {req_val} {req_u_disp}"
                    )
            else:  # LOWER_BETTER
                if off_val > req_val:
                    failed_details.append(
                        f"Incumplimiento técnico: {attr_label} ofrecido/a de {off_val} {off_u_disp} excede el plazo máximo requerido de {req_val} {req_u_disp}"
                    )
                elif off_val < req_val:
                    improvement_details.append(
                        f"Mejora técnica acreditada y validada documentalmente: {attr_label} ofrecido/a de {off_val} {off_u_disp} es menor al plazo máximo requerido de {req_val} {req_u_disp}"
                    )
                else:
                    passed_details.append(
                        f"Cumplimiento técnico acreditado y validado documentalmente: {attr_label} de {off_val} {off_u_disp} cumple el plazo requerido de {req_val} {req_u_disp}"
                    )

        # AGGREGATION RULES:
        # 1. Any FAILED => FAILED (confidence 1.0)
        if failed_details:
            return {
                "status": "FAILED",
                "explanation": "; ".join(failed_details),
                "confidence": 1.0
            }

        # 2. Any Ambiguity / Contradiction / Range / Upper Limit / Temporal Mismatch => REQUIERE_REVISION (confidence 0.5)
        if ambiguous_details:
            return {
                "status": "REQUIERE_REVISION",
                "explanation": "; ".join(ambiguous_details) + ". Requiere revisión técnica humana.",
                "confidence": 0.5
            }

        # 3. All passed/improvement:
        if improvement_details:
            all_details = improvement_details + passed_details
            return {
                "status": "IMPROVEMENT",
                "explanation": "; ".join(all_details),
                "confidence": 1.0
            }

        if passed_details:
            return {
                "status": "PASSED",
                "explanation": "; ".join(passed_details),
                "confidence": 1.0
            }

        return {
            "status": "REQUIERE_REVISION",
            "explanation": "Evidencia documental verificada; pendiente de revisión técnica humana para determinar cumplimiento frente al requisito.",
            "confidence": 0.5
        }
