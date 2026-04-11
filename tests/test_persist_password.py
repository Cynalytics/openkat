from __future__ import annotations

import importlib.util
import os
import stat
import sys
import types

import pytest


def load_persist_password_module(role_root, monkeypatch):
    ansible_module = types.ModuleType("ansible")
    module_utils = types.ModuleType("ansible.module_utils")
    basic = types.ModuleType("ansible.module_utils.basic")

    class DummyAnsibleModule:  # pragma: no cover - only used to satisfy imports
        def __init__(self, *args, **kwargs):
            self.params = {}
            self.check_mode = False

        def fail_json(self, **kwargs):
            raise AssertionError(kwargs)

        def exit_json(self, **kwargs):
            return kwargs

    basic.AnsibleModule = DummyAnsibleModule

    monkeypatch.setitem(sys.modules, "ansible", ansible_module)
    monkeypatch.setitem(sys.modules, "ansible.module_utils", module_utils)
    monkeypatch.setitem(sys.modules, "ansible.module_utils.basic", basic)

    module_path = role_root / "library" / "persist_password.py"
    spec = importlib.util.spec_from_file_location("persist_password", module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def persist_password_module(role_root, monkeypatch):
    return load_persist_password_module(role_root, monkeypatch)


def test_build_charset_combines_requested_sets(persist_password_module):
    chars = persist_password_module.build_charset("ascii_letters,digits")

    assert "a" in chars
    assert "Z" in chars
    assert "5" in chars


def test_build_charset_rejects_unknown_tokens(persist_password_module):
    with pytest.raises(ValueError, match="Invalid chars tokens"):
        persist_password_module.build_charset("digits,unknown")


def test_validate_variable_rejects_invalid_names(persist_password_module):
    with pytest.raises(ValueError, match="must be non-empty"):
        persist_password_module.validate_variable("BAD NAME")

    with pytest.raises(ValueError, match="must be non-empty"):
        persist_password_module.validate_variable("BAD=NAME")


def test_generate_password_uses_requested_charset(persist_password_module):
    password = persist_password_module.generate_password(24, "abc123")

    assert len(password) == 24
    assert set(password) <= set("abc123")


def test_generate_password_rejects_non_positive_length(persist_password_module):
    with pytest.raises(ValueError, match="positive integer"):
        persist_password_module.generate_password(0, "abc")


def test_write_atomic_creates_file_with_expected_mode(tmp_path, persist_password_module):
    target = tmp_path / "openkat" / "creds.env"

    persist_password_module.write_atomic(
        str(target),
        ["OPENKAT_PASSWORD=secret-value"],
        0o600,
        -1,
        -1,
    )

    assert target.read_text() == "OPENKAT_PASSWORD=secret-value\n"
    assert stat.S_IMODE(target.stat().st_mode) == 0o600


def test_read_env_lines_returns_file_lines(tmp_path, persist_password_module):
    target = tmp_path / "passwords.env"
    target.write_text("FIRST=value\nSECOND=other\n", encoding="utf-8")

    lines = persist_password_module.read_env_lines(str(target))

    assert lines == ["FIRST=value", "SECOND=other"]


def test_resolve_uid_gid_accepts_numeric_values(persist_password_module):
    uid, gid = persist_password_module.resolve_uid_gid(str(os.getuid()), str(os.getgid()))

    assert uid == os.getuid()
    assert gid == os.getgid()