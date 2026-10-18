import sys
import os
import argparse
import hashlib

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

        # 3. TenantConfiguration for mega_tenant
        tenant_config = db.query(TenantConfiguration).filter_by(tenant_id="mega_tenant").first()
        if not tenant_config:
            tenant_config = TenantConfiguration(tenant_id="mega_tenant", telemetry_opt_in=False)
            db.add(tenant_config)
            db.commit()

        # 4. Mandatory OutputTemplate (CONDICIONES) - Filtrado por tipo, entidad y version
        template_cond = db.query(OutputTemplate).filter_by(
            type="CONDICIONES", entity_name="Abast-gp", version="1.0"
        ).first()
        if not template_cond:
            # Si existia uno antiguo sin filtrar por tipo pero con mismos datos
            legacy_t = db.query(OutputTemplate).filter_by(entity_name="Abast-gp", version="1.0").first()
            if legacy_t and legacy_t.type == "CONDICIONES":
                template_cond = legacy_t
            else:
                template_cond = OutputTemplate(
                    type="CONDICIONES",
                    version="1.0",
                    entity_name="Abast-gp",
                    content="Plantilla base generada",
                    status="ACTIVE"
                )
                db.add(template_cond)
                db.commit()

        # 5. Mandatory OutputTemplate (INFORME_TECNICO_EVALUACION) - P13 (12 Secciones Canónicas)
        template_p13 = db.query(OutputTemplate).filter_by(
            type="INFORME_TECNICO_EVALUACION", entity_name="Abast-gp", version="1.0"
        ).first()
        p13_content = """<div class="technical-evaluation-report">
  <div class="report-header">
    <h1>INFORME TÉCNICO DE EVALUACIÓN Y SELECCIÓN INTERNA</h1>
    <p class="subtitle">Expediente: {{ case_code }} | Versión: {{ version_number }}</p>
  </div>
  <section class="report-section section-1">
    <h2>1. Expediente y Objeto de la Contratación</h2>
    {{ section_1_case_object_html }}
  </section>
  <section class="report-section section-2">
    <h2>2. Antecedentes Administrativos</h2>
    {{ section_2_antecedents_html }}
  </section>
  <section class="report-section section-3">
    <h2>3. Documentos Examinados y Hashes Sustentados</h2>
    {{ section_3_examined_documents_html }}
  </section>
  <section class="report-section section-4">
    <h2>4. Proveedores Participantes y Ofertas Presentadas</h2>
    {{ section_4_suppliers_offers_html }}
  </section>
  <section class="report-section section-5">
    <h2>5. Matriz de Evaluación Técnica y Cumplimiento de Requisitos</h2>
    {{ section_5_requirements_matrix_html }}
  </section>
  <section class="report-section section-6">
    <h2>6. Trazabilidad de Evidencias Acreditadas</h2>
    {{ section_6_evidence_traceability_html }}
  </section>
  <section class="report-section section-7">
    <h2>7. Resultados No Conformes y Revisión Humana</h2>
    {{ section_7_non_conformities_html }}
  </section>
  <section class="report-section section-8">
    <h2>8. Mejoras y Factores Diferenciadores Acreditados</h2>
    {{ section_8_improvements_html }}
  </section>
  <section class="report-section section-9">
    <h2>9. Condiciones Contractuales</h2>
    {{ section_9_contractual_conditions_html }}
  </section>
  <section class="report-section section-10">
    <h2>10. Evaluación Económica y Valor por Dinero (VfM)</h2>
    {{ section_10_economic_vfm_html }}
  </section>
  <section class="report-section section-11">
    <h2>11. Motivación y Cadena de Selección Interna</h2>
    {{ section_11_motivation_selection_html }}
  </section>
  <section class="report-section section-12">
    <h2>12. Conclusión, Alcance Legal, Firmas y Auditoría</h2>
    {{ section_12_conclusion_audit_html }}
  </section>
</div>"""
        p13_checksum = hashlib.sha256(p13_content.encode('utf-8')).hexdigest()

        if not template_p13:
            template_p13 = OutputTemplate(
                type="INFORME_TECNICO_EVALUACION",
                version="1.0",
                entity_name="Abast-gp",
                content=p13_content,
                checksum=p13_checksum,
                status="ACTIVE"
            )
            db.add(template_p13)
            db.commit()
        else:
            # Sincronizar contenido y checksum
            template_p13.content = p13_content
            template_p13.checksum = p13_checksum
            db.commit()

        # 6. CiiuCatalog - Minimum viable entry
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
        # Sequence alignment guard to prevent primary key desynchronization
        from sqlalchemy import text
        for seq_table in ["suppliers", "users", "case_files", "supplier_offers"]:
            try:
                db.execute(text(f"SELECT setval('{seq_table}_id_seq', COALESCE((SELECT MAX(id) FROM {seq_table}), 1));"))
                db.commit()
            except Exception:
                db.rollback()

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
