"""Test package initialization.
Guarantees test execution always targets an isolated test database,
preventing any mutation or pollution of production data/gymsis.db.
"""

import os
import tempfile

TEST_DB_PATH = os.path.join(tempfile.gettempdir(), "gymsis_test_suite.db")
os.environ.setdefault("GYMSIS_SQLITE_PATH", TEST_DB_PATH)
