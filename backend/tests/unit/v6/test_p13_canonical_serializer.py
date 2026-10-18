import os
import time
import json
import pytest
import hashlib
from decimal import Decimal
from datetime import datetime, timezone, timedelta
from app.services.v6.reporting.canonical_serializer import CanonicalSerializer

def test_canonical_serializer_deterministic_keys():
    data1 = {"z": 1, "a": 2, "m": {"b": 3, "a": 4}}
    data2 = {"a": 2, "m": {"a": 4, "b": 3}, "z": 1}
    bytes1 = CanonicalSerializer.serialize_to_bytes(data1)
    bytes2 = CanonicalSerializer.serialize_to_bytes(data2)
    assert bytes1 == bytes2
    assert CanonicalSerializer.calculate_hash(bytes1) == CanonicalSerializer.calculate_hash(bytes2)

def test_canonical_serializer_decimal_precision():
    d = Decimal("12345.6700")
    data = {"amount": d}
    serialized = CanonicalSerializer.serialize_to_bytes(data).decode("utf-8")
    assert '"amount":"12345.6700"' in serialized
    # Decimal quantize scale tests
    d2 = Decimal("5000.50").quantize(Decimal("0.01"))
    data2 = {"price": d2}
    serialized2 = CanonicalSerializer.serialize_to_bytes(data2).decode("utf-8")
    assert '"price":"5000.50"' in serialized2

def test_canonical_serializer_iso_utc_dates():
    dt = datetime(2026, 10, 17, 10, 30, 0, tzinfo=timezone.utc)
    data = {"date": dt}
    serialized = CanonicalSerializer.serialize_to_bytes(data).decode("utf-8")
    assert '"date":"2026-10-17T10:30:00Z"' in serialized

def test_canonical_serializer_timezone_independence():
    """
    Verifica que datetimes con offset de zona horaria (ej. UTC-5 America/Lima o UTC+9 Asia/Tokyo)
    se conviertan de manera determinista al mismo instante UTC exacto terminado en 'Z'.
    """
    tz_minus_5 = timezone(timedelta(hours=-5))
    tz_plus_9 = timezone(timedelta(hours=9))

    dt_utc = datetime(2026, 10, 17, 12, 0, 0, tzinfo=timezone.utc)
    dt_lima = datetime(2026, 10, 17, 7, 0, 0, tzinfo=tz_minus_5)   # Mismo instante que 12:00 UTC
    dt_tokyo = datetime(2026, 10, 17, 21, 0, 0, tzinfo=tz_plus_9) # Mismo instante que 12:00 UTC

    bytes_utc = CanonicalSerializer.serialize_to_bytes({"timestamp": dt_utc})
    bytes_lima = CanonicalSerializer.serialize_to_bytes({"timestamp": dt_lima})
    bytes_tokyo = CanonicalSerializer.serialize_to_bytes({"timestamp": dt_tokyo})

    assert bytes_utc == bytes_lima == bytes_tokyo
    assert json.loads(bytes_utc.decode("utf-8")) == {"timestamp": "2026-10-17T12:00:00Z"}
    assert CanonicalSerializer.calculate_hash(bytes_utc) == CanonicalSerializer.calculate_hash(bytes_lima)

def test_canonical_serializer_explicit_null():
    data = {"nullable_field": None, "present_field": "val"}
    serialized = CanonicalSerializer.serialize_to_bytes(data).decode("utf-8")
    assert '"nullable_field":null' in serialized

def test_canonical_serializer_tamper_detection():
    data = {"case_id": 100, "supplier": "Empresa SAC", "price": Decimal("5000.00")}
    original_hash = CanonicalSerializer.calculate_hash(data)
    
    # Manipular dato
    tampered_data = {"case_id": 100, "supplier": "Empresa SAC", "price": Decimal("5000.01")}
    tampered_hash = CanonicalSerializer.calculate_hash(tampered_data)
    
    assert original_hash != tampered_hash
    assert CanonicalSerializer.verify_hash(data, original_hash) is True
    assert CanonicalSerializer.verify_hash(tampered_data, original_hash) is False

def test_canonical_serializer_jsonb_roundtrip():
    """
    Verifica que el snapshot mantenga el mismo hash antes y después de simular la persistencia en PostgreSQL JSONB.
    """
    original_snapshot = {
        "case_id": 42,
        "amount": Decimal("15420.50"),
        "date": datetime(2026, 10, 17, 14, 0, 0, tzinfo=timezone.utc),
        "nested": {"status": "APPROVED", "items": [1, 2, 3]}
    }
    hash_before = CanonicalSerializer.calculate_hash(original_snapshot)

    # Simulación de paso por columna JSONB (serialización a JSON string y parseo de vuelta a dict)
    jsonb_str = json.dumps(CanonicalSerializer._normalize_obj(original_snapshot))
    deserialized_from_db = json.loads(jsonb_str)

    hash_after = CanonicalSerializer.calculate_hash(deserialized_from_db)
    assert hash_before == hash_after, f"Discrepancia de hash JSONB: {hash_before} vs {hash_after}"

def test_canonical_serializer_unicode_preservation():
    r"""
    Verifica la preservación íntegra de caracteres Unicode (tildes, eñes, símbolos) sin secuencias \uXXXX.
    """
    data = {
        "title": "Evaluación Técnica de Adquisición de Papel Bond",
        "supplier_name": "Corporación Gráfica Ñandú S.A.C.",
        "notes": "Conformidad técnica — 100% verificado con estándar € internacional & 日本語"
    }
    raw_bytes = CanonicalSerializer.serialize_to_bytes(data)
    utf8_str = raw_bytes.decode("utf-8")
    assert "\\u" not in utf8_str
    assert "Ñandú" in utf8_str
    assert "Evaluación" in utf8_str
    assert "—" in utf8_str
    assert "日本語" in utf8_str

def test_canonical_serializer_negative_and_variable_scale_decimals():
    """
    Verifica que importes negativos y decimales de escala variable (0, 1, 4, 6 decimales)
    se serialicen con precisión exacta y sin aplicar indiscriminadamente 2 decimales ni notación científica.
    """
    data = {
        "negative_adjustment": Decimal("-150.75"),
        "ratio_vfm": Decimal("0.0001"),
        "factor_weight": Decimal("1.5"),
        "integer_units": Decimal("100"),
        "high_precision_rate": Decimal("0.123456")
    }
    raw_bytes = CanonicalSerializer.serialize_to_bytes(data)
    decoded = raw_bytes.decode("utf-8")
    assert '"negative_adjustment":"-150.75"' in decoded
    assert '"ratio_vfm":"0.0001"' in decoded
    assert '"factor_weight":"1.5"' in decoded
    assert '"integer_units":"100"' in decoded
    assert '"high_precision_rate":"0.123456"' in decoded

def test_canonical_serializer_real_postgresql_persistence(db_session):
    """
    Prueba de persistencia real en PostgreSQL:
    Inserta GeneratedOutput con source_snapshot normalizado, realiza commit real,
    recupera de la base de datos y verifica que el hash recalculado coincida exactamente con el original.
    """
    from app.models.v6.generated_output import GeneratedOutput
    from app.models.domain import CaseFile, User, Tenant
    from app.models.v6.output_template import OutputTemplate

    # Setup mínimo en DB real
    tenant = db_session.query(Tenant).filter_by(id="mega_tenant").first()
    if not tenant:
        tenant = Tenant(id="mega_tenant", name="Mega Tenant")
        db_session.add(tenant)
        db_session.flush()

    user = db_session.query(User).filter_by(id=1).first()
    case = CaseFile(title="Caso Test Hash JSONB", contract_type="BIENES", status="APPROVED", tenant_id="mega_tenant", assigned_to_user_id=user.id)
    db_session.add(case)
    db_session.flush()

    template = db_session.query(OutputTemplate).filter_by(type="INFORME_TECNICO_EVALUACION", version="1.0").first()
    if not template:
        template = OutputTemplate(
            type="INFORME_TECNICO_EVALUACION",
            version="1.0",
            entity_name="Abast-gp",
            content="<div>template</div>",
            status="ACTIVE"
        )
        db_session.add(template)
        db_session.flush()

    complex_snapshot = {
        "case_id": case.id,
        "case_code": "CASO-JSONB-2026",
        "winner": {
            "supplier_name": "Soluciones Técnicas & Cía. S.A.C.",
            "total_amount": Decimal("24500.85"),
            "vfm_ratio": Decimal("0.0035"),
            "discount_adjustment": Decimal("-500.00"),
            "weight": Decimal("1.75")
        },
        "created_at": datetime(2026, 10, 17, 18, 0, 0, tzinfo=timezone.utc),
        "nullable_audit_note": None
    }

    # Calcular hash original sobre bytes canónicos
    expected_hash = CanonicalSerializer.calculate_hash(complex_snapshot)
    normalized_for_db = CanonicalSerializer._normalize_obj(complex_snapshot)

    output = GeneratedOutput(
        case_id=case.id,
        template_id=template.id,
        template_version=template.version,
        content_rendered="<p>Test</p>",
        generation_hash=expected_hash,
        generated_by=user.id,
        accuracy_gate_result="PASS",
        source_snapshot=normalized_for_db,
        status="GENERATED",
        version_number=1,
        report_kind="INFORME_TECNICO_EVALUACION",
        snapshot_hash=expected_hash
    )
    db_session.add(output)
    db_session.commit()
    output_id = output.id

    # Limpiar caché de sesión y consultar directamente de PostgreSQL
    db_session.expire_all()
    queried = db_session.query(GeneratedOutput).filter_by(id=output_id).first()
    assert queried is not None

    # Recalcular hash a partir del JSONB leído de PostgreSQL
    recalculated_hash = CanonicalSerializer.calculate_hash(queried.source_snapshot)
    assert recalculated_hash == expected_hash, f"Hash discrepante tras persistencia real en PostgreSQL JSONB: {recalculated_hash} != {expected_hash}"
    assert CanonicalSerializer.verify_hash(queried.source_snapshot, expected_hash) is True

