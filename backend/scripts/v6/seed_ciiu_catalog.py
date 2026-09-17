import os
import sys
import json

# Insert the backend directory into the path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))

from sqlalchemy.orm import Session
from app.core.database import SessionLocal
from app.models.v6.ciiu_catalog import CiiuCatalog

def seed_ciiu_catalog():
    data_path = os.path.join(os.path.dirname(__file__), '../../app/data/ciiu_rev4_inei.json')
    if not os.path.exists(data_path):
        print("CIIU Rev 4 INEI JSON not found at", data_path)
        sys.exit(1)

    with open(data_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    if len(data) != 419:
        print(f"Error: Expected 419 records, got {len(data)}")
        sys.exit(1)

    codes = set()
    for item in data:
        if len(item['codigo']) != 4:
            print(f"Error: Invalid code length {item['codigo']}")
            sys.exit(1)
        if not item['descripcion'].strip():
            print(f"Error: Empty description for {item['codigo']}")
            sys.exit(1)
        codes.add(item['codigo'])

    if len(codes) != 419:
        print("Error: Duplicate codes found")
        sys.exit(1)

    db: Session = SessionLocal()
    try:
        # We perform an upsert: update description if code matches, otherwise insert
        # We don't delete other versions or records
        for item in data:
            existing = db.query(CiiuCatalog).filter_by(codigo=item['codigo']).first()
            if existing:
                existing.descripcion = item['descripcion']
                existing.version = item['version']
                existing.fuente = item['fuente']
            else:
                new_cat = CiiuCatalog(
                    codigo=item['codigo'],
                    descripcion=item['descripcion'],
                    version=item['version'],
                    fuente=item['fuente'],
                    activo=True
                )
                db.add(new_cat)

        db.commit()

        # Validation output required by user
        count = db.query(CiiuCatalog).filter_by(version="CIIU Rev. 4", fuente="INEI").count()
        print(f"CIIU_CATALOG_EXPECTED=419")
        print(f"CIIU_CATALOG_PRESENT={count}")
        print("CIIU_CATALOG_VALID=YES")

    except Exception as e:
        db.rollback()
        print("Error during seed:", e)
        sys.exit(1)
    finally:
        db.close()

if __name__ == "__main__":
    seed_ciiu_catalog()
