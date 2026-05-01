"""Ensure tests use in-memory DB and isolated settings before any app import."""

import os

os.environ.setdefault("ENVIRONMENT", "testing")
