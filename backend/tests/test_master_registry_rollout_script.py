from __future__ import annotations

import argparse
import importlib.util
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parent.parent / "scripts" / "run_master_registry_rollout.py"


def _load_script_module():
    spec = importlib.util.spec_from_file_location("run_master_registry_rollout", SCRIPT_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_build_dsn_prefers_registry_env(monkeypatch):
    module = _load_script_module()
    args = argparse.Namespace(
        host=None,
        port=None,
        user=None,
        password=None,
        database=None,
    )

    monkeypatch.setenv("REGISTRY_POSTGRES_USER", "registry_user")
    monkeypatch.setenv("REGISTRY_POSTGRES_PASSWORD", "registry_pass")
    monkeypatch.setenv("REGISTRY_POSTGRES_HOST", "registry-host")
    monkeypatch.setenv("REGISTRY_POSTGRES_PORT", "5544")
    monkeypatch.setenv("REGISTRY_POSTGRES_DB", "registry_db")

    dsn = module.build_dsn(args)

    assert dsn == "postgresql://registry_user:registry_pass@registry-host:5544/registry_db"


def test_build_dsn_falls_back_to_postgres_env(monkeypatch):
    module = _load_script_module()
    args = argparse.Namespace(
        host=None,
        port=None,
        user=None,
        password=None,
        database=None,
    )

    monkeypatch.delenv("REGISTRY_POSTGRES_USER", raising=False)
    monkeypatch.delenv("REGISTRY_POSTGRES_PASSWORD", raising=False)
    monkeypatch.delenv("REGISTRY_POSTGRES_HOST", raising=False)
    monkeypatch.delenv("REGISTRY_POSTGRES_PORT", raising=False)
    monkeypatch.delenv("REGISTRY_POSTGRES_DB", raising=False)
    monkeypatch.setenv("POSTGRES_USER", "app_user")
    monkeypatch.setenv("POSTGRES_PASSWORD", "app_pass")
    monkeypatch.setenv("POSTGRES_HOST", "127.0.0.1")
    monkeypatch.setenv("POSTGRES_PORT", "5432")
    monkeypatch.setenv("POSTGRES_DB", "app_db")

    dsn = module.build_dsn(args)

    assert dsn == "postgresql://app_user:app_pass@127.0.0.1:5432/app_db"
