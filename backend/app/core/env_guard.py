import os
from sqlalchemy.engine import make_url

class EnvGuardError(Exception):
    pass

def validate_migration_environment(app_env: str, db_url: str, env_vars: dict) -> None:
    """
    Este guard es un preflight técnico fail-closed. No constituye por sí solo
    autorización humana u operativa para ejecutar migraciones en producción.
    """
    if not app_env:
        raise EnvGuardError("APP_ENV is required but missing.")
        
    app_env = app_env.strip().lower()
    
    if not db_url:
        raise EnvGuardError("Database URL is required but missing.")
        
    try:
        parsed_url = make_url(db_url)
    except Exception as e:
        raise EnvGuardError(f"Failed to parse database URL: {e}")
        
    db_name = parsed_url.database.strip() if parsed_url.database else ""
    host = parsed_url.host.strip() if parsed_url.host else ""
    port = parsed_url.port or 5432
    
    if not db_name:
        raise EnvGuardError("Database name missing in URL.")
        
    if app_env == 'test':
        if 'abst_gp' in db_url or 'abst_gp' in db_name:
            raise EnvGuardError("TEST environment cannot connect to 'abst_gp'.")
        return # Test is allowed otherwise

    if app_env == 'production':
        expected_host = env_vars.get('EXPECTED_DATABASE_HOST', '').strip()
        expected_port = str(env_vars.get('EXPECTED_DATABASE_PORT', '')).strip()
        expected_name = env_vars.get('EXPECTED_DATABASE_NAME', '').strip()
        expected_target = env_vars.get('EXPECTED_ALEMBIC_TARGET', '').strip()
        change_id = env_vars.get('MIGRATION_CHANGE_ID', '').strip()
        
        if not change_id:
            raise EnvGuardError("MIGRATION_CHANGE_ID is required for production.")
        if not expected_host:
            raise EnvGuardError("EXPECTED_DATABASE_HOST is required for production.")
        if not expected_port:
            raise EnvGuardError("EXPECTED_DATABASE_PORT is required for production.")
        if not expected_name:
            raise EnvGuardError("EXPECTED_DATABASE_NAME is required for production.")
        if not expected_target:
            raise EnvGuardError("EXPECTED_ALEMBIC_TARGET is required for production.")
            
        if host != expected_host:
            raise EnvGuardError(f"Host mismatch. Expected '{expected_host}', got '{host}'")
        if str(port) != expected_port:
            raise EnvGuardError(f"Port mismatch. Expected '{expected_port}', got '{port}'")
        if db_name != expected_name:
            raise EnvGuardError(f"Database mismatch. Expected '{expected_name}', got '{db_name}'")
            
        return
        
    if app_env == 'local':
        if host != 'db':
            raise EnvGuardError(f"Local environment requires host 'db', got '{host}'")
        if str(port) != '5432':
            raise EnvGuardError(f"Local environment requires port '5432', got '{port}'")
        if db_name != 'abst_gp':
            raise EnvGuardError(f"Local environment requires database 'abst_gp', got '{db_name}'")
        return

    if app_env == 'lan':
        if host != 'db':
            raise EnvGuardError(f"LAN environment requires host 'db', got '{host}'")
        if str(port) != '5432':
            raise EnvGuardError(f"LAN environment requires port '5432', got '{port}'")
        allowed_lan_dbs = ('abst_gp_pilot', 'abst_gp_lan')
        if db_name not in allowed_lan_dbs:
            raise EnvGuardError(f"LAN environment requires database in {allowed_lan_dbs}, got '{db_name}'")
        return

    raise EnvGuardError(f"Unknown or unauthorized environment: {app_env}")
