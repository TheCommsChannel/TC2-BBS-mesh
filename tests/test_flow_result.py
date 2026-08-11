"""Tests for FlowResult and its outcome constructors.

Candidate 01: a flow's answer carries exactly one outcome, so the flag
combinations the old fields allowed (goto *and* enter, goto *and* keep) cannot
be written. These tests lock the shape.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flows.base import (
    FlowResult, Stay, End, Keep, Goto, Enter, stay, end, keep, goto, enter,
)


def test_each_helper_builds_its_outcome():
    assert stay({"step": 1}).outcome == Stay({"step": 1})
    assert end().outcome == End()
    assert keep().outcome == Keep()
    assert goto("bbs").outcome == Goto("bbs")
    assert enter("MAIL").outcome == Enter("MAIL")


def test_helpers_carry_replies_and_notifications():
    r = keep(replies=["hi"], notifications=[("!bob", "psst")])
    assert r.replies == ["hi"]
    assert r.notifications == [("!bob", "psst")]
    assert isinstance(r.outcome, Keep)


def test_the_old_flag_fields_are_gone():
    """There is no goto / enter / keep_state / next_state field to set two of."""
    r = stay({"step": 1})
    for gone in ("goto", "enter", "keep_state", "next_state"):
        assert not hasattr(r, gone), f"FlowResult still exposes {gone}"


def test_a_result_has_exactly_one_outcome():
    # The outcome is a single value; there is nowhere to write a second one.
    assert FlowResult().__dataclass_fields__.keys() == {"replies", "notifications", "outcome"}


def test_outcomes_are_frozen():
    import dataclasses
    try:
        Goto("bbs").menu = "main"
    except dataclasses.FrozenInstanceError:
        return
    raise AssertionError("outcomes should be frozen")


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
