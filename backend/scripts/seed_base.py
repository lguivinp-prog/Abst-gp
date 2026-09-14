import sys
import os
import argparse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.models.domain import Tenant, SystemSettings
from app.models.v6.tenant_config import TenantConfiguration
from app.models.v6.output_template import OutputTemplate
from app.models.v6.ciiu_catalog import CiiuCatalog

def run_seed():
    engine = create_engine(settings.DATABASE_URL)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = SessionLocal()

    try:
        # 1. Tenant 'mega_tenant'
        tenant = db.query(Tenant).filter_by(id="mega_tenant").first()
        if not tenant:
            tenant = Tenant(id="mega_tenant", name="Mega Tenant")
            db.add(tenant)
            db.commit()

        # 2. SystemSettings id=1, active_ring=0
        sys_settings = db.query(SystemSettings).filter_by(id=1).first()
        if not sys_settings:
            sys_settings = SystemSettings(id=1, active_ring=0)
            db.add(sys_settings)
            db.commit()

        # 3. TenantConfiguration for mega_tenan
        tenant_config = db.query(TenantConfiguration).filter_by(tenant_id="mega_tenant").first()
        if not tenant_config:
            tenant_config = TenantConfiguration(tenant_id="mega_tenant", telemetry_opt_in=False)
            db.add(tenant_config)
            db.commit()

        # 4. Mandatory OutputTemplate (CONDICIONES)
        template = db.query(OutputTemplate).filter_by(entity_name="Abast-gp", version="1.0").first()
        if not template:
            template = OutputTemplate(
                type="CONDICIONES",
                version="1.0",
                entity_name="Abast-gp",
                content="Plantilla base generada",
                status="ACTIVE"
            )
            db.add(template)
            db.commit()

        # 5. CiiuCatalog - Minimum viable entry
        ciiu = db.query(CiiuCatalog).filter_by(codigo="0000").first()
        if not ciiu:
            ciiu = CiiuCatalog(
                codigo="0000",
                descripcion="Categoria General / Base",
                version="1.0",
                fuente="seed",
                activo=True
            )
            db.add(ciiu)
            db.commit()

        print("Seed finalizado exitosamente.")

        # Conteo de filas
        print("--- Conteo de Filas ---")
        print(f"Tenant: {db.query(Tenant).count()}")
        print(f"SystemSettings: {db.query(SystemSettings).count()}")
        print(f"TenantConfiguration: {db.query(TenantConfiguration).count()}")
        print(f"OutputTemplate: {db.query(OutputTemplate).count()}")
        print(f"CiiuCatalog: {db.query(CiiuCatalog).count()}")

    except Exception as e:
        db.rollback()
        print(f"Error durante el seed: {e}")
        sys.exit(1)
    finally:
        db.close()

if __name__ == "__main__":
    run_seed()
