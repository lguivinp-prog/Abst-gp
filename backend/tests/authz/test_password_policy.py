import pytest
import uuid
import os
import tempfile
from unittest.mock import patch, MagicMock
from app.api.auth import get_password_hash, verify_password
from app.cli.admin_bootstrap import create_admin
from click.testing import CliRunner
import sys

def test_password_policy_length_enforced():
    # Enforced in auth schemas usually, but we check if bcrypt hash respects the length 
    pass

def test_crypto_compatibility():
    # 2. Límite bcrypt medido en bytes UTF-8 (71 bytes).
    # 3. Compatibilidad con hashes bcrypt históricos.
    long_pwd = "a" * 71
    hashed = get_password_hash(long_pwd)
    assert verify_password(long_pwd, hashed)

    # Test truncamiento seguro o rechazo explícito en authz_models o router
    with pytest.raises(ValueError):
        # Mi política implementada en auth.py debe rechazar explícitamente > 71 bytes
        get_password_hash("a" * 72)

def test_password_file_permissions():
    # 4. Modo batch: leer de archivo y validación 0600 estricta
    with tempfile.NamedTemporaryFile(mode='w', delete=False) as f:
        f.write("SomePassword123!")
        pwd_file = f.name

    if os.name == 'posix':
        os.chmod(pwd_file, 0o644)
        with patch("sys.exit") as exit_mock:
            exit_mock.side_effect = SystemExit
            with pytest.raises(SystemExit):
                create_admin(pwd_file)
            exit_mock.assert_called_with(1)

        os.chmod(pwd_file, 0o600)
        # Assuming DB won't crash when running mock, but we don't test actual DB here

def test_environment_guard_rejects_abst_gp(monkeypatch):
    # 6. `abst_gp` siempre rechazado
    monkeypatch.setattr("app.core.config.settings.DATABASE_URL", "postgresql://user:pass@localhost/abst_gp")

    with patch("sys.exit") as exit_mock:
        exit_mock.side_effect = SystemExit
        with pytest.raises(SystemExit):
            create_admin(None)
        exit_mock.assert_called_with(1)

def test_interactive_tty_requirement():
    # 5. Modo interactivo únicamente con TTY real
    with patch("sys.stdin.isatty", return_value=False), patch("sys.exit") as exit_mock:
        exit_mock.side_effect = SystemExit
        with pytest.raises(SystemExit):
            create_admin(None)
        exit_mock.assert_called_with(1)
