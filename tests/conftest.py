import os
import tempfile

import pytest

# Point the app at a throwaway SQLite file before anything imports database.py,
# which builds its engine at import time.
_TEST_DB = os.path.join(tempfile.gettempdir(), "terpenomics_test.db")
if os.path.exists(_TEST_DB):
    os.remove(_TEST_DB)

# Assigned, not setdefault: these must win over whatever the surrounding
# environment already has. A real DATABASE_URL in the environment (Render, a
# shell that sourced .env, CI) would otherwise silently point the whole suite
# at production, and the Supabase keys at a live project.
os.environ["DATABASE_URL"] = f"sqlite:///{_TEST_DB}"
os.environ["SUPABASE_URL"] = "https://test.supabase.co"
os.environ["SUPABASE_ANON_KEY"] = "test-anon-key"
os.environ["SUPABASE_SERVICE_ROLE_KEY"] = "test-service-key"


def pytest_configure(config):
    config.addinivalue_line("markers", "live: makes real HTTP requests to dispensary APIs")
