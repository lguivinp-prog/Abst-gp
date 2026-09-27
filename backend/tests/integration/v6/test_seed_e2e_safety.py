import pytest
import os
import subprocess
import sys

def test_seed_e2e_aborts_without_opt_in():
    '''
    CASE 1: Ensure that without ALLOW_E2E_SEED=true, the script exits immediately with non-zero
    and does not execute database mutation.
    '''
    script_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))),
        "scripts",
        "seed_e2e.py"
    )

    env = os.environ.copy()
    # Explicitly remove the flag if it happens to be present
    if "ALLOW_E2E_SEED" in env:
        del env["ALLOW_E2E_SEED"]

    # We pass APP_ENV=test just to verify it still fails due to missing ALLOW_E2E_SEED
    env["APP_ENV"] = "test"

    result = subprocess.run([sys.executable, script_path], env=env, capture_output=True, text=True)

    assert result.returncode != 0
    assert "ABORT: E2E seed cannot run without ALLOW_E2E_SEED=true explicit opt-in." in result.stdout

def test_seed_e2e_aborts_without_app_env_test():
    '''
    Ensure that even with ALLOW_E2E_SEED=true, if APP_ENV != test, it aborts.
    '''
    script_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))),
        "scripts",
        "seed_e2e.py"
    )

    env = os.environ.copy()
    env["ALLOW_E2E_SEED"] = "true"
    env["APP_ENV"] = "production"

    result = subprocess.run([sys.executable, script_path], env=env, capture_output=True, text=True)

    assert result.returncode != 0
    assert "ABORT: E2E seed can only run in APP_ENV=test." in result.stdout

def test_seed_e2e_aborts_with_missing_database_url():
    script_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))),
        "scripts",
        "seed_e2e.py"
    )

    env = os.environ.copy()
    env["ALLOW_E2E_SEED"] = "true"
    env["APP_ENV"] = "test"
    if "DATABASE_URL" in env:
        del env["DATABASE_URL"]

    result = subprocess.run([sys.executable, script_path], env=env, capture_output=True, text=True)

    assert result.returncode != 0
    assert "ABORT: DATABASE_URL is not set." in result.stdout

def test_seed_e2e_aborts_with_invalid_database_url():
    script_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))),
        "scripts",
        "seed_e2e.py"
    )

    env = os.environ.copy()
    env["ALLOW_E2E_SEED"] = "true"
    env["APP_ENV"] = "test"
    env["DATABASE_URL"] = "not_a_url_at_all"

    result = subprocess.run([sys.executable, script_path], env=env, capture_output=True, text=True)

    assert result.returncode != 0
    assert "ABORT: Invalid DATABASE_URL format." in result.stdout

def test_seed_e2e_aborts_with_wrong_host():
    script_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))),
        "scripts",
        "seed_e2e.py"
    )

    env = os.environ.copy()
    env["ALLOW_E2E_SEED"] = "true"
    env["APP_ENV"] = "test"
    # test_db but wrong host
    env["DATABASE_URL"] = "postgresql://user:pass@production-db:5432/test_db"

    result = subprocess.run([sys.executable, script_path], env=env, capture_output=True, text=True)

    assert result.returncode != 0
    assert "ABORT: E2E seed can only run against a test database (host=db-test, database=test_db)." in result.stdout

def test_seed_e2e_aborts_with_wrong_database():
    script_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))),
        "scripts",
        "seed_e2e.py"
    )

    env = os.environ.copy()
    env["ALLOW_E2E_SEED"] = "true"
    env["APP_ENV"] = "test"
    # db-test but wrong db
    env["DATABASE_URL"] = "postgresql://user:pass@db-test:5432/production_db"

    result = subprocess.run([sys.executable, script_path], env=env, capture_output=True, text=True)

    assert result.returncode != 0
    assert "ABORT: E2E seed can only run against a test database (host=db-test, database=test_db)." in result.stdout
