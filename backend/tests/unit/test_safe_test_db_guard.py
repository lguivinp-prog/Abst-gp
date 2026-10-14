import pytest
from unittest.mock import MagicMock, patch
from _pytest.outcomes import Exit
from tests.conftest import ensure_safe_test_db


class MockUrl:
    def __init__(self, host=None, url_str="postgresql://user:pass@host/db"):
        self.host = host
        self._url_str = url_str

    def __str__(self):
        return self._url_str


def make_mock_conn(db_name: str, host: str = "db-test"):
    conn = MagicMock()
    conn.engine.url = MockUrl(host=host, url_str=f"postgresql://user:pass@{host}/{db_name}")
    conn.execute.return_value.scalar.return_value = db_name
    return conn


def test_guard_allows_standard_test_db(monkeypatch):
    monkeypatch.setenv("APP_ENV", "test")
    conn = make_mock_conn("test_db", host="db-test")
    # Should complete without calling pytest.exit
    ensure_safe_test_db(conn)


def test_guard_allows_exact_dr_db_on_authorized_host(monkeypatch):
    monkeypatch.setenv("APP_ENV", "test")
    conn = make_mock_conn("dr_db", host="db-dr")
    # Should complete without calling pytest.exit
    ensure_safe_test_db(conn)


@pytest.mark.parametrize("invalid_dr_name", [
    "dr",
    "prod_dr_db",
    "my_dr_db",
    "dr_staging",
    "dr_dev",
    "dr_data",
    "database_dr",
])
def test_guard_rejects_substring_dr_only(monkeypatch, invalid_dr_name):
    monkeypatch.setenv("APP_ENV", "test")
    conn = make_mock_conn(invalid_dr_name, host="db-dr")
    with pytest.raises(Exit, match=r"does not look like a test database"):
        ensure_safe_test_db(conn)


@pytest.mark.parametrize("protected_name", [
    "abst_gp",
    "abst_gp_test",
    "test_abst_gp",
    "production",
    "production_test",
    "test_production",
])
def test_guard_rejects_protected_dbs(monkeypatch, protected_name):
    monkeypatch.setenv("APP_ENV", "test")
    conn = make_mock_conn(protected_name, host="db-test")
    with pytest.raises(Exit, match=r"is protected"):
        ensure_safe_test_db(conn)


@pytest.mark.parametrize("unauthorized_host", [
    "localhost",
    "127.0.0.1",
    "db-test",
    "remote-host",
    "10.0.0.5",
    None,
])
def test_guard_rejects_dr_db_on_unauthorized_host(monkeypatch, unauthorized_host):
    monkeypatch.setenv("APP_ENV", "test")
    conn = make_mock_conn("dr_db", host=unauthorized_host)
    with pytest.raises(Exit, match=r"DR database 'dr_db' is only permitted on host 'db-dr'"):
        ensure_safe_test_db(conn)


@pytest.mark.parametrize("invalid_env", [
    "production",
    "development",
    "staging",
    "prod",
    "",
])
def test_guard_rejects_non_test_app_env(monkeypatch, invalid_env):
    monkeypatch.setenv("APP_ENV", invalid_env)
    conn = make_mock_conn("test_db", host="db-test")
    with pytest.raises(Exit, match=r"must be 'test' for destructive operations"):
        ensure_safe_test_db(conn)


def test_guard_rejects_missing_app_env(monkeypatch):
    monkeypatch.delenv("APP_ENV", raising=False)
    conn = make_mock_conn("test_db", host="db-test")
    with pytest.raises(Exit, match=r"must be 'test' for destructive operations"):
        ensure_safe_test_db(conn)


def test_guard_rejects_empty_db_name(monkeypatch):
    monkeypatch.setenv("APP_ENV", "test")
    conn = make_mock_conn("", host="db-test")
    conn.execute.return_value.scalar.return_value = None
    with pytest.raises(Exit, match=r"Could not determine database name"):
        ensure_safe_test_db(conn)
