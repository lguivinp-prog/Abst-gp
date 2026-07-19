set -e

pytest --collect-only -q

pytest -q -ra -rxX \
  -o xfail_strict=true \
  -W error::pytest.PytestUnhandledThreadExceptionWarning

pytest -q -ra -rxX \
  -o xfail_strict=true \
  -W error::pytest.PytestUnhandledThreadExceptionWarning
