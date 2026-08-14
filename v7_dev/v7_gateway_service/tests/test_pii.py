from services.pii_detection import pii_detector
from services.masking import masking_service
from services.policy import policy_service

def test_pii_detection():
    text = "Mi DNI es 12345678 y mi RUC es 10123456789."
    matches = pii_detector.detect(text)
    assert len(matches) == 2
    labels = [m["label"] for m in matches]
    assert "DNI" in labels
    assert "RUC" in labels

def test_masking_service():
    text = "DNI 12345678 oculto"
    masked = masking_service.mask_text(text)
    assert masked == "DNI [DNI_MASKED] oculto"

def test_policy_fail_closed():
    # Simulate a bug in masking where a 9 digit number leaks
    leaked_text = "DNI [DNI_MASKED] y un numero 123456789 que se escapo"
    decision = policy_service.evaluate_request(leaked_text)
    assert decision == "BLOCK" # Policy caught the 8+ digit leak
