"""conftest.py — set dummy env vars so imports work without real credentials."""
import os
os.environ.setdefault("GEMINI_API_KEY", "test-key")
os.environ.setdefault("DATABASE_URL",   "postgresql://test:test@localhost:5432/test")
