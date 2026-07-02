"""Tests for silica.config."""

import pytest
from unittest.mock import patch
from pathlib import Path

import silica.config as cfg


@pytest.fixture(autouse=True)
def isolated_config(tmp_path, monkeypatch):
    config_path = tmp_path / "config.toml"
    monkeypatch.setattr(cfg, "_CONFIG_PATH", config_path)
    monkeypatch.setattr(cfg, "_CONFIG_DIR", tmp_path)
    yield config_path


def test_load_returns_defaults_when_missing():
    result = cfg.load()
    assert "tools" in result
    assert "clients" in result
    assert "oss_cad_suite" in result


def test_load_returns_defaults_on_invalid_toml(isolated_config):
    isolated_config.write_text("this is not valid toml ::::")
    result = cfg.load()
    assert "tools" in result


def test_load_warns_on_invalid_toml(isolated_config, caplog):
    import logging
    isolated_config.write_text("this is not valid toml ::::")
    with caplog.at_level(logging.WARNING, logger="silica.config"):
        cfg.load()
    assert any("config" in rec.message.lower() for rec in caplog.records)


def test_load_returns_independent_copy_of_defaults():
    first = cfg.load()
    first["tools"]["simulation"]["priority"].append("mutated")
    second = cfg.load()
    assert second["tools"]["simulation"]["priority"] == []
    assert cfg._DEFAULTS["tools"]["simulation"]["priority"] == []


def test_save_creates_file(isolated_config):
    cfg.save({"tools": {}, "clients": {}})
    assert isolated_config.exists()


def test_save_and_load_roundtrip(isolated_config):
    data = {"tools": {"simulation": {"priority": ["verilator"]}}, "clients": {}}
    cfg.save(data)
    loaded = cfg.load()
    assert loaded["tools"]["simulation"]["priority"] == ["verilator"]


def test_config_path_is_toml():
    assert str(cfg.config_path()).endswith("config.toml")


def test_load_defaults_have_expected_tool_categories():
    result = cfg.load()
    tools = result.get("tools", {})
    for category in ("simulation", "synthesis", "place_route", "formal",
                     "lint", "waveform", "program"):
        assert category in tools, f"Missing category: {category}"
