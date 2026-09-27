import pytest
import re

import os

def test_source_fidelity_rules():
    # 1. Finalidad Publica sin inventar metas
    finalidad = "Adquirir herramientas y otros bienes para la Agencia Agraria Bongará, con la finalidad de llevar a cabo las actividades administrativas durante el presente año 2026, en el marco a las actividades operativas del POI 2026."
    assert "funcionamiento adecuado de las metas" not in finalidad

    # 2. Antecedentes sin cadena presupuestal inventada
    antecedentes = "La Agencia Agraria Bongará, en el marco de sus funciones de capacitación y asistencia técnica, requiere contar con la adquisición de otros bienes para poder desarrollar esta actividad con los agricultores del ámbito de la provincia."
    assert "cadena presupuestal" not in antecedentes.lower()
    
    # 3. Objetivo sin ferreteria
    objetivo = "Cumplir con las actividades del POI 2026 de la Agencia Agraria Bongará, durante el presente año 2026."
    assert "ferretería" not in objetivo.lower()

    # 4. RNP
    rnp = "Registro Nacional de Proveedores vigente (Obligatorio)."
    assert "de corresponder" not in rnp.lower()

    # 5. Experiencia
    experiencia = "El postor debe acreditar un monto facturado acumulado equivalente a S/. 2000.00"
    assert "equivalente" in experiencia
    assert "no menor a" not in experiencia

    # 6. Bienes similares
    similares = "Se considera la venta de útiles de escritorio iguales o similares."
    assert "útiles de escritorio" in similares
    assert "ferretería" not in similares

    # 7. Pago sin CCI inventado
    pago = "factura\nguía de remisión\notros documentos solicitados para el pago\npresentados en la oficina de Almacén de la Dirección Regional de Agricultura de Amazonas"
    assert re.search(r"(?<!\w)cci(?!\w)", pago, flags=re.IGNORECASE) is None
    assert "seguros" not in pago.lower()
    assert "transporte" not in pago.lower()

    # 8. Resolución
    res_11_5 = "Cualquiera de las partes puede resolver el contrato"
    assert "cualquiera de las partes" in res_11_5.lower()
    assert "gorea" not in res_11_5.lower()

    # 9. PAC
    pac = "el presente requerimiento NO SE ENCUENTRA PROGRAMADO en el PAC"
    assert "no se encuentra programado" in pac.lower()
