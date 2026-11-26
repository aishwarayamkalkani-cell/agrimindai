import os
import shutil
import tempfile

# One throw-away data directory for the whole test session (set before the app is imported).
_TMP = tempfile.mkdtemp(prefix="agrimind_test_")
os.environ["AGRIMIND_STORE"] = _TMP


def pytest_sessionfinish(session, exitstatus):
    shutil.rmtree(_TMP, ignore_errors=True)
