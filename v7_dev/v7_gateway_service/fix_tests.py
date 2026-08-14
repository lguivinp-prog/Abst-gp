import os

# Fix test_sprint56_final.py
with open("tests/test_sprint56_final.py", "r") as f:
    content = f.read()
content = content.replace("assert passed == False", "assert passed == False\n    rollout_controller.celery_backlog = False")
with open("tests/test_sprint56_final.py", "w") as f:
    f.write(content)

# Fix test_universal_gate_matrix.py
with open("tests/test_universal_gate_matrix.py", "r") as f:
    content = f.read()
if "original_validate = rollout_controller.validate_universal_gate" not in content:
    content = content.replace("def setup_function():", "original_validate = None\ndef setup_function():\n    global original_validate\n    original_validate = rollout_controller.validate_universal_gate")
    content = content.replace("rollout_controller.validate_universal_gate = strict_validate", "rollout_controller.validate_universal_gate = strict_validate\n\ndef teardown_function():\n    rollout_controller.validate_universal_gate = original_validate")
with open("tests/test_universal_gate_matrix.py", "w") as f:
    f.write(content)

# Fix test_security_adversarial.py
with open("tests/test_security_adversarial.py", "r") as f:
    content = f.read()
if "original_validate =" not in content:
    content = content.replace("def test_wave_blocked_on_violation():", "def test_wave_blocked_on_violation():\n    original_validate = rollout_controller.validate_universal_gate")
    content = content.replace("assert \"isolation\" in reason", "assert \"isolation\" in reason\n    rollout_controller.validate_universal_gate = original_validate\n    rollout_controller.active_isolation_violations = 0")
with open("tests/test_security_adversarial.py", "w") as f:
    f.write(content)

# Reset singleton states that might be leaking
reset_script = """
import pytest
from services.rollout_controller import rollout_controller
from services.capacity_guard import capacity_guard

@pytest.fixture(autouse=True)
def reset_singletons():
    capacity_guard.total_capacity_available = 15000.0
    rollout_controller.active_isolation_violations = 0
    rollout_controller.current_wave = 0
"""
with open("tests/conftest.py", "w") as f:
    f.write(reset_script)
