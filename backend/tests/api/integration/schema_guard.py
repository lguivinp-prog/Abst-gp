import os
from pathlib import Path
from dataclasses import dataclass
from typing import Set, Tuple
from sqlalchemy import inspect, create_engine
from alembic.config import Config
from alembic.script import ScriptDirectory
from alembic.runtime.migration import MigrationContext

class SchemaGuardError(Exception):
    pass

@dataclass
class SchemaReport:
    current_heads: Set[str]
    expected_heads: Set[str]
    missing_tables: Tuple[str, ...]

CRITICAL_TABLES = (
    "alembic_version",
    "users",
    "case_files",
    "uploaded_documents",
    "parsed_sections",
    "ocr_processing_runs"
)

def assert_alembic_schema_current(engine):
    current_dir = Path(__file__).resolve().parent
    # Go up from backend/tests/api/integration to backend
    backend_dir = current_dir.parent.parent.parent
    alembic_ini_path = backend_dir / "alembic.ini"
    
    if not alembic_ini_path.is_file():
        raise SchemaGuardError(f"Alembic configuration file not found at: {alembic_ini_path}")
        
    alembic_cfg = Config(str(alembic_ini_path))
    script_location = alembic_cfg.get_main_option("script_location")
    if not script_location:
        raise SchemaGuardError("script_location not found in alembic.ini")
        
    alembic_cfg.set_main_option("script_location", str(backend_dir / script_location))
    
    script_directory = ScriptDirectory.from_config(alembic_cfg)
    
    with engine.connect() as connection:
        migration_context = MigrationContext.configure(connection)
        
        expected_heads = frozenset(script_directory.get_heads())
        current_heads = frozenset(migration_context.get_current_heads())
        
        inspector = inspect(connection)
        missing_tables = tuple(
            table for table in CRITICAL_TABLES 
            if not inspector.has_table(table)
        )
        
        report = SchemaReport(
            current_heads=set(current_heads),
            expected_heads=set(expected_heads),
            missing_tables=missing_tables
        )
        
        if not expected_heads:
            raise SchemaGuardError("No expected heads found in Alembic script directory.")
            
        if "alembic_version" in missing_tables:
            raise SchemaGuardError("alembic_version table does not exist. Schema is not initialized by Alembic.")
            
        if not current_heads:
            raise SchemaGuardError("No current heads applied. Database has no applied migrations.")
            
        if current_heads != expected_heads:
            raise SchemaGuardError(
                f"Migration mismatch. Expected heads: {expected_heads}, Current heads: {current_heads}"
            )
            
        if missing_tables:
            raise SchemaGuardError(f"Critical tables missing in the database schema: {missing_tables}")
            
        return report
