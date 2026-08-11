"""Unit tests for StatsFlow — the pure Flow shape.

No interface, no database, no sending. Feed a message + state + Deps, assert
on the returned FlowResult. This is what every migrated flow's tests look like.
"""

import os
import sys

# Run from anywhere: put the repo root on the path before importing the modules
# under test. Keeps `python tests/test_x.py` working alongside pytest.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flows.base import Deps, Stay, Goto
from flows.stats import StatsFlow


def roster(*nodes):
    """Build a node roster keyed by id from (id, hw, role, last_heard) tuples."""
    out = {}
    for i, (hw, role, last) in enumerate(nodes):
        out[f"!n{i}"] = {
            "num": 100 + i,
            "user": {"shortName": f"N{i}", "longName": f"Node {i}",
                     "hwModel": hw, "role": role},
            "lastHeard": last,
        }
    return out


STEP1 = {"command": "STATS", "step": 1}


def test_node_summary_counts_all_time():
    deps = Deps(roster=roster(("TBEAM", "CLIENT", None),
                              ("HELTEC", "ROUTER", None)))
    r = StatsFlow().advance("n", STEP1, deps)
    assert "Total nodes seen:" in r.replies[0]
    assert "All time: 2" in r.replies[0]
    assert r.replies[1].startswith("📊Stats Menu📊")
    assert r.outcome == Stay(STEP1)


def test_hardware_summary_groups_models():
    deps = Deps(roster=roster(("TBEAM", "CLIENT", None),
                              ("TBEAM", "CLIENT", None),
                              ("HELTEC", "CLIENT", None)))
    r = StatsFlow().advance("h", STEP1, deps)
    assert "TBEAM: 2" in r.replies[0]
    assert "HELTEC: 1" in r.replies[0]


def test_role_summary_groups_roles():
    deps = Deps(roster=roster(("TBEAM", "CLIENT", None),
                              ("TBEAM", "ROUTER", None)))
    r = StatsFlow().advance("r", STEP1, deps)
    assert "CLIENT: 1" in r.replies[0]
    assert "ROUTER: 1" in r.replies[0]


def test_exit_requests_main_menu():
    r = StatsFlow().advance("x", STEP1, Deps())
    assert r.outcome == Goto("main")
    assert r.replies == []


def test_repeated_x_suffix_collapses_to_exit():
    r = StatsFlow().advance("nx", STEP1, Deps())
    # "nx" collapses to "n", not exit.
    assert not isinstance(r.outcome, Goto)


def test_unknown_input_stays_silent():
    r = StatsFlow().advance("z", STEP1, Deps(roster=roster(("TBEAM", "CLIENT", None))))
    assert r.replies == []
    assert r.outcome == Stay(STEP1)
    assert not isinstance(r.outcome, Goto)


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
