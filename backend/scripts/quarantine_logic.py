def classify_user_tenant(user_row) -> dict:
    """
    Pure function to determine how a user should be migrated.
    
    Returns a dict with:
      - action: 'ASSIGN' or 'QUARANTINE'
      - tenant_id: (if ASSIGN)
      - reason_code: (if QUARANTINE)
      - evidence: (if QUARANTINE)
    """
    username = getattr(user_row, "username", "")
    
    # Heurística simulada: Usuarios que no podemos resolver de forma segura.
    if username.startswith("ambiguous_") or username.startswith("legacy_"):
        return {
            "action": "QUARANTINE",
            "reason_code": "unresolved_legacy_mapping",
            "evidence": {"username": username, "heuristics_failed": ["name_match", "domain_match"]}
        }
        
    # Por defecto, resolvemos al mega_tenant para usuarios normales.
    return {
        "action": "ASSIGN",
        "tenant_id": "mega_tenant"
    }
