import pytest
import os
from unittest.mock import MagicMock
from tests.conftest import ensure_safe_test_db

def test_db_guard_rejects_abst_gp(monkeypatch):
    monkeypatch.setenv("APP_ENV", "test")
    
    mock_conn = MagicMock()
    mock_scalar = MagicMock(return_value="abst_gp")
    mock_conn.execute.return_value.scalar = mock_scalar
    with pytest.raises(BaseException) as excinfo:
        ensure_safe_test_db(mock_conn)
    
    assert "protected" in str(excinfo.value)
    assert "abst_gp" in str(excinfo.value)

def test_db_guard_rejects_non_test_db_name(monkeypatch):
    monkeypatch.setenv("APP_ENV", "test")
    
    mock_conn = MagicMock()
    mock_scalar = MagicMock(return_value="some_other_db")
    mock_conn.execute.return_value.scalar = mock_scalar
    with pytest.raises(BaseException) as excinfo:
        ensure_safe_test_db(mock_conn)
    
    assert "must contain 'test'" in str(excinfo.value)

def test_db_guard_rejects_non_test_app_env(monkeypatch):
    monkeypatch.setenv("APP_ENV", "local")
    
    mock_conn = MagicMock()
    mock_scalar = MagicMock(return_value="my_test_db")
    mock_conn.execute.return_value.scalar = mock_scalar
    with pytest.raises(BaseException) as excinfo:
        ensure_safe_test_db(mock_conn)
    
    assert "APP_ENV is 'local'" in str(excinfo.value)

def test_db_guard_allows_test_db(monkeypatch):
    monkeypatch.setenv("APP_ENV", "test")
    
    mock_conn = MagicMock()
    mock_scalar = MagicMock(return_value="v6_rc_test")
    mock_conn.execute.return_value.scalar = mock_scalar
    # Should not raise any exception
    ensure_safe_test_db(mock_conn)
