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
    for category in ("simulation", "synthesis", "formal", "lint"):
        assert category in tools, f"Missing category: {category}"
