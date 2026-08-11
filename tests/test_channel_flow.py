"""Unit tests for ChannelFlow — pure, with a fake store."""

import os
import sys

# Run from anywhere: put the repo root on the path before importing the modules
# under test. Keeps `python tests/test_x.py` working alongside pytest.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flows.base import Deps, Stay, End, Keep, Goto
from flows.channel import ChannelFlow, CHANNEL_MENU


class FakeStore:
    def __init__(self, channels=None):
        self._channels = channels or []
        self.added = []

    def get_channels(self):
        return self._channels

    def add_channel(self, name, url):
        self.added.append((name, url))
        self._channels.append((name, url))


def deps(store=None):
    return Deps(store=store or FakeStore())


def st(command, step=None, **extra):
    state = {"command": command}
    if step is not None:
        state["step"] = step
    state.update(extra)
    return state


# --- directory menu --------------------------------------------------------

def test_view_empty_directory_reshows_menu():
    r = ChannelFlow().advance("v", st("CHANNEL_DIRECTORY", 1), deps())
    assert r.replies == ["No channels available in the directory.", CHANNEL_MENU]
    assert r.outcome.state["step"] == 1


def test_view_lists_channels_and_advances():
    store = FakeStore(channels=[("Net", "url1"), ("Backup", "url2")])
    r = ChannelFlow().advance("v", st("CHANNEL_DIRECTORY", 1), deps(store))
    assert "[0] Net" in r.replies[0]
    assert "[1] Backup" in r.replies[0]
    assert r.outcome.state["step"] == 2


def test_post_prompts_for_name():
    r = ChannelFlow().advance("p", st("CHANNEL_DIRECTORY", 1), deps())
    assert "Name your channel" in r.replies[0]
    assert r.outcome.state["step"] == 3


def test_unknown_menu_choice_is_silent():
    r = ChannelFlow().advance("z", st("CHANNEL_DIRECTORY", 1), deps())
    assert r.replies == []
    assert r.outcome.state["step"] == 1


def test_repeated_x_suffix_collapses():
    r = ChannelFlow().advance("vx", st("CHANNEL_DIRECTORY", 1), deps())
    # "vx" collapses to "v" -> view, not exit
    assert not isinstance(r.outcome, Goto)
    assert "No channels available" in r.replies[0]


# --- view a channel by index ----------------------------------------------

def test_view_valid_index_shows_url_then_menu():
    store = FakeStore(channels=[("Net", "url1")])
    r = ChannelFlow().advance("0", st("CHANNEL_DIRECTORY", 2), deps(store))
    assert "Channel Name: Net" in r.replies[0]
    assert "url1" in r.replies[0]
    assert r.replies[1] == CHANNEL_MENU
    assert r.outcome.state["step"] == 1


def test_view_out_of_range_just_reshows_menu():
    store = FakeStore(channels=[("Net", "url1")])
    r = ChannelFlow().advance("9", st("CHANNEL_DIRECTORY", 2), deps(store))
    assert r.replies == [CHANNEL_MENU]


# --- posting a channel -----------------------------------------------------

def test_name_then_url_adds_and_syncs():
    store = FakeStore()
    r = ChannelFlow().advance("MyNet", st("CHANNEL_DIRECTORY", 3), deps(store))
    assert "URL or PSK" in r.replies[0]
    assert r.outcome == Stay({"command": "CHANNEL_DIRECTORY", "step": 4, "channel_name": "MyNet"})

    state = r.outcome.state
    r = ChannelFlow().advance("https://x", state, deps(store))
    # The menu path now replicates, same as the CHP,, quick command.
    assert store.added == [("MyNet", "https://x")]
    assert "has been added to the directory" in r.replies[0]
    assert r.replies[1] == CHANNEL_MENU
    assert r.outcome.state["step"] == 1


# --- numbered read (seeded by the CHL quick command) ----------------------

def test_read_numbered_valid():
    state = st("LIST_CHANNELS", 1, channels=[("Net", "url1")])
    r = ChannelFlow().advance("1", state, deps())
    assert r.replies == ["Channel Name: Net\nChannel URL: url1"]
    assert r.outcome == End()


def test_read_numbered_out_of_range():
    state = st("LIST_CHANNELS", 1, channels=[("Net", "url1")])
    r = ChannelFlow().advance("5", state, deps())
    assert "Invalid channel number" in r.replies[0]
    assert r.outcome == Stay(state)


def test_read_numbered_non_numeric():
    state = st("LIST_CHANNELS", 1, channels=[("Net", "url1")])
    r = ChannelFlow().advance("abc", state, deps())
    assert "Invalid input" in r.replies[0]
    assert r.outcome == Stay(state)


def test_check_channel_topic_reads_the_same_way():
    state = st("CHECK_CHANNEL", 1, channels=[("Net", "url1")])
    r = ChannelFlow().advance("1", state, deps())
    assert "Channel Name: Net" in r.replies[0]


# --- CHP,, quick post ------------------------------------------------------

def test_quick_post_adds_channel():
    """The old parser split on '|' and could never succeed."""
    store = FakeStore()
    r = ChannelFlow().quick_post("chp,,MyNet,,https://example/x", deps(store))
    assert store.added == [("MyNet", "https://example/x")]
    assert r.replies == ["Channel 'MyNet' has been added to the directory."]
    assert isinstance(r.outcome, Keep)


def test_quick_post_keeps_url_containing_commas():
    store = FakeStore()
    ChannelFlow().quick_post("chp,,Net,,https://x?a=1,,b=2", deps(store))
    assert store.added[0][1] == "https://x?a=1,,b=2"


def test_quick_post_usage_on_bad_format():
    r = ChannelFlow().quick_post("chp,,NoUrl", deps())
    assert "Post Channel Quick Command format" in r.replies[0]
    assert isinstance(r.outcome, Keep)


def test_quick_post_usage_on_empty_fields():
    r = ChannelFlow().quick_post("chp,,,,", deps())
    assert "Post Channel Quick Command format" in r.replies[0]


# --- CHL quick list --------------------------------------------------------

def test_quick_list_empty():
    r = ChannelFlow().quick_list("chl", deps())
    assert r.replies == ["No channels available in the directory."]
    assert isinstance(r.outcome, Keep)


def test_quick_list_awaits_a_number():
    store = FakeStore(channels=[("Net", "url1")])
    r = ChannelFlow().quick_list("chl", deps(store))
    assert "01. Name: Net" in r.replies[0]
    assert r.outcome.state["command"] == "LIST_CHANNELS"


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
