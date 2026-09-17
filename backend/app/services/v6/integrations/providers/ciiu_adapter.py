import re
from typing import Dict, Any, List
from sqlalchemy.orm import Session
import requests
from .base_provider import ValidationResult

class CIIUProvider:
    def _normalize(self, text: str) -> str:
        if not text: return ""
        text = text.upper()
        text = re.sub(r'[ÁÀÄ]', 'A', text)
        text = re.sub(r'[ÉÈË]', 'E', text)
        text = re.sub(r'[ÍÌÏ]', 'I', text)
        text = re.sub(r'[ÓÒÖ]', 'O', text)
        text = re.sub(r'[ÚÙÜ]', 'U', text)
        return re.sub(r'[^A-Z0-9\s]', '', text).strip()

    def _get_inei_detail(self, codigo: str) -> Dict[str, Any]:
        import requests
        import html
        url = f"https://proyectos.inei.gob.pe/CIIU/frm_lista_notas.asp?wc_cod={codigo}"
        try:
            resp = requests.get(url, timeout=15)
            if resp.status_code != 200:
                return {"detail_retrieved": False, "detail_status": "UNAVAILABLE", "inei_detail_url": url}

            html_text = resp.text
            html_clean = re.sub(r'[\r\n]+', ' ', html_text)
            html_clean = re.sub(r'<br\s*/?>', ' ', html_clean, flags=re.IGNORECASE)

            rows = re.findall(r'<tr[^>]*>(.*?)</tr>', html_clean, flags=re.IGNORECASE)
            if len(rows) < 2:
                return {"detail_retrieved": False, "detail_status": "UNAVAILABLE", "inei_detail_url": url}

            header_row = rows[0]
            header_cells = re.findall(r'<td[^>]*>(.*?)</td>', header_row, flags=re.IGNORECASE)

            headers = []
            for cell in header_cells:
                text = re.sub(r'<[^>]+>', '', cell).strip()
                headers.append(text)

            data_row = rows[1]
            data_cells = re.findall(r'<td[^>]*>(.*?)</td>', data_row, flags=re.IGNORECASE)

            result = {
                "detail_retrieved": True,
                "detail_status": "AVAILABLE",
                "inei_detail_url": url,
                "incluye": None,
                "no_incluye": None
            }

            for idx, h in enumerate(headers):
                if idx < len(data_cells):
                    text = re.sub(r'<[^>]+>', '', data_cells[idx])
                    text = html.unescape(text).strip()
                    if text == "":
                        text = None

                    if "Incluye" in h and "No" not in h:
                        result["incluye"] = text
                    elif "No Incluye" in h:
                        result["no_incluye"] = text

            return result

        except Exception as e:
            return {"detail_retrieved": False, "detail_status": "UNAVAILABLE", "inei_detail_url": url, "error": str(e)}

    def _jaccard(self, a: str, b: str) -> float:
        set_a = set(a.split())
        set_b = set(b.split())
        if not set_a or not set_b: return 0.0
        return len(set_a.intersection(set_b)) / len(set_a.union(set_b))

    def validate(self, db: Session, sunat_activities: List[Dict[str, Any]], activities_complete: bool, expected_keywords: str) -> ValidationResult:
        if not sunat_activities:
            return ValidationResult(
                status="MANUAL_REQUIRED",
                source="CIIU_MATCH",
                payload={"error": "No hay actividades de SUNAT para evaluar."}
            )

        from app.models.v6.ciiu_catalog import CiiuCatalog
        catalog = db.query(CiiuCatalog).all()
        if not catalog:
            return ValidationResult(
                status="MANUAL_REQUIRED",
                source="CIIU_MATCH",
                payload={"error": "Catálogo CIIU no está cargado."}
            )

        results = []
        global_status = "PASSED"
        inei_cache = {}

        for act_dict in sunat_activities:
            act_text = act_dict.get("descripcion_sunat", "")
            tipo = act_dict.get("tipo", "DESCONOCIDO")
            norm_act = self._normalize(act_text)
            match_method = "NONE"
            matched_code = None
            descripcion_inei = None
            sim_score = 0.0

            # Extract 4-digit code if exists
            match = re.search(r'\b\d{4}\b', act_text)
            if match:
                code = match.group()
                cat_match = next((c for c in catalog if c.codigo == code), None)
                if cat_match:
                    match_method = "EXACT_CODE"
                    matched_code = cat_match.codigo
                    descripcion_inei = cat_match.descripcion

            if match_method == "NONE":
                best_sim = 0.0
                best_match = None
                for c in catalog:
                    sim = self._jaccard(norm_act, self._normalize(c.descripcion))
                    if sim > best_sim:
                        best_sim = sim
                        best_match = c

                if best_match and best_sim > 0.2:
                    match_method = "JACCARD"
                    matched_code = best_match.codigo
                    descripcion_inei = best_match.descripcion
                    sim_score = best_sim

            res_status = "PASSED" if match_method != "NONE" else "REVIEW_REQUIRED"
            if res_status == "REVIEW_REQUIRED":
                global_status = "REVIEW_REQUIRED"

            res_dict = {
                "tipo": tipo,
                "actividad_sunat": act_text,
                "codigo_ciiu": matched_code,
                "descripcion_inei": descripcion_inei,
                "status": res_status,
                "classifier_source": "INEI",
                "classifier_version": "CIIU Rev. 4",
                "match_method": match_method,
                "classification_verified": True if matched_code else False,
                "detail_retrieved": False,
                "detail_status": "UNAVAILABLE",
                "inei_detail_url": None,
                "incluye": None,
                "no_incluye": None
            }

            if matched_code:
                if matched_code not in inei_cache:
                    inei_cache[matched_code] = self._get_inei_detail(matched_code)

                inei_res = inei_cache[matched_code]
                res_dict["detail_retrieved"] = inei_res.get("detail_retrieved", False)
                res_dict["detail_status"] = inei_res.get("detail_status", "UNAVAILABLE")
                res_dict["inei_detail_url"] = inei_res.get("inei_detail_url")
                res_dict["incluye"] = inei_res.get("incluye")
                res_dict["no_incluye"] = inei_res.get("no_incluye")

            results.append(res_dict)

        if global_status == "PASSED" and (not activities_complete or len(results) == 0):
            global_status = "REVIEW_REQUIRED"

        return ValidationResult(
            status=global_status,
            source="CIIU_MATCH",
            payload={
                "activities_complete": activities_complete,
                "total_activities": len(results),
                "results": results
            }
        )
