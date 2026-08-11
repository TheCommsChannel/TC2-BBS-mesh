"""Tests for reading configuration into a Config value.

Config is read once from a file and passed down; nothing caches it in a module
global (see docs/adr/0004). These tests write a temp .ini and load it, so they
never touch the repo's own config.ini.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import dataclasses
import tempfile

import settings
from settings import load


def _load(ini, fortunes=None):
    """Write ini (and optional fortunes) to temp files and load a Config."""
    with tempfile.TemporaryDirectory() as tmp:
        ini_path = os.path.join(tmp, "config.ini")
        with open(ini_path, "w") as handle:
            handle.write(ini)
        fortunes_path = os.path.join(tmp, "fortunes.txt")
        if fortunes is not None:
            with open(fortunes_path, "w") as handle:
                handle.write(fortunes)
        return load(ini_path, fortunes_file=fortunes_path)


FULL = """
[menu]
main_menu_items = Q, B, U, X
bbs_menu_items = M, B, C, J, X
utilities_menu_items = S, F, W, X

[sync]
bbs_nodes = !peer1,!peer2

[allow_list]
allowed_nodes = !boss

[js8call]
host = 192.168.1.10
port = 2442
db_file = js8call.db
js8groups = @NET, @EMCOMM
js8urgent = @URGENT
store_messages = false
"""

MINIMAL = "[menu]\nmain_menu_items = X\nbbs_menu_items = X\nutilities_menu_items = X\n"


def test_menus_are_parsed_and_stripped():
    config = _load(FULL)
    assert config.menus.main == ["Q", "B", "U", "X"]
    assert config.menus.bbs == ["M", "B", "C", "J", "X"]
    assert config.menus.utilities == ["S", "F", "W", "X"]


def test_node_lists_are_parsed():
    config = _load(FULL)
    assert config.bbs_nodes == ["!peer1", "!peer2"]
    assert config.allowed_nodes == ["!boss"]


def test_js8_settings_are_parsed():
    config = _load(FULL)
    assert config.js8.host == "192.168.1.10"
    assert config.js8.port == 2442
    assert config.js8.db_path == "js8call.db"
    assert config.js8.groups == ["@NET", "@EMCOMM"]
    assert config.js8.urgent == ["@URGENT"]
    assert config.js8.store_messages is False


def test_fortunes_are_read_and_stripped():
    config = _load(FULL, fortunes="  be brief  \n\nstay curious\n")
    assert config.fortunes == ["be brief", "stay curious"]


def test_missing_fortunes_file_is_empty():
    config = _load(FULL)      # no fortunes written
    assert config.fortunes == []


def test_missing_sections_degrade_to_empty():
    config = _load(MINIMAL)
    assert config.bbs_nodes == []
    assert config.allowed_nodes == []
    assert config.js8.db_path is None
    assert config.js8.host is None
    assert config.js8.store_messages is True      # the documented default
    assert config.fortunes == []


def test_config_is_frozen():
    config = _load(FULL)
    try:
        config.bbs_nodes = ["!evil"]
    except dataclasses.FrozenInstanceError:
        return
    raise AssertionError("Config should be frozen")


def test_missing_menu_section_degrades_to_empty_menus():
    """A config with no [menu] section yields empty menus, not a KeyError.

    The old menus() used bracket access and raised; _items() falls back to ''.
    """
    config = _load("[sync]\nbbs_nodes = !p\n")
    assert config.menus.main == []
    assert config.menus.bbs == []
    assert config.menus.utilities == []


def test_settings_holds_no_mutable_module_state():
    """No configure(), no reset(), no cache — configuration is a value."""
    assert not hasattr(settings, "configure")
    assert not hasattr(settings, "reset")


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    failed = 0
    for fn in fns:
        try:
            fn()
            print(f"ok  {fn.__name__}")
        except AssertionError as e:
            failed += 1
            print(f"FAIL {fn.__name__}: {e}")
    print(f"\n{len(fns) - failed}/{len(fns)} passed")
