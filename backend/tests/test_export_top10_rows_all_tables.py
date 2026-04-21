import argparse

from scripts.export_top10_rows_all_tables import (
    build_dsn,
    parse_schemas,
    quote_identifier,
)


def test_quote_identifier_escapes_double_quotes() -> None:
    assert quote_identifier('bad"name') == '"bad""name"'


def test_parse_schemas_filters_blanks() -> None:
    assert parse_schemas("public, srsadmin, , custom ") == ["public", "srsadmin", "custom"]


def test_parse_schemas_default_when_empty() -> None:
    assert parse_schemas("  ,  ") == ["public"]


def test_build_dsn_prefers_args_over_env(monkeypatch) -> None:
    monkeypatch.setenv("POSTGRES_USER", "env_user")
    monkeypatch.setenv("POSTGRES_PASSWORD", "env_pass")
    monkeypatch.setenv("POSTGRES_HOST", "env_host")
    monkeypatch.setenv("POSTGRES_PORT", "6543")
    monkeypatch.setenv("POSTGRES_DB", "env_db")

    args = argparse.Namespace(
        user="arg_user",
        password="arg_pass",
        host="arg_host",
        port=7777,
        database="arg_db",
    )
    assert build_dsn(args) == "postgresql://arg_user:arg_pass@arg_host:7777/arg_db"
