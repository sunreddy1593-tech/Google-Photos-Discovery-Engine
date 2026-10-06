"""Queue and research/publication sequencing verified without live requests."""
from contextlib import contextmanager
import subprocess
import threading
import sys
import uuid

import pytest
from scripts.run_queued_discovery import run_queued, scheduled_queue


def test_queue_covers_research_and_publication(tmp_path):
    events = []
    @contextmanager
    def queue():
        events.append("acquire")
        yield
        events.append("release")
    def run(args, **kwargs):
        events.append("research" if args[-1] == "schedule" else "publication")
        return subprocess.CompletedProcess(args, 0)
    assert run_queued(tmp_path, queue=queue, run=run) == 0
    assert events == ["acquire", "research", "publication", "release"]


@pytest.mark.parametrize("research_exit,publish_exit", [(1, 0), (0, 1), (0, 0)])
def test_exit_code_and_no_research_retry(tmp_path, research_exit, publish_exit):
    commands = []
    @contextmanager
    def queue():
        yield
    def run(args, **kwargs):
        commands.append(args)
        return subprocess.CompletedProcess(args, research_exit if args[-1] == "schedule" else publish_exit)
    assert run_queued(tmp_path, queue=queue, run=run) == research_exit
    assert len(commands) == (1 if research_exit else 2)


@pytest.mark.skipif(sys.platform != "win32", reason="Windows kernel mutex")
def test_windows_mutex_serializes_distinct_workers():
    name = "Local\\DiscoveryQueueTest-" + uuid.uuid4().hex
    held = threading.Event()
    release = threading.Event()
    second_entered = threading.Event()
    attempted = threading.Event()
    errors = []
    def first():
        try:
            with scheduled_queue(name):
                held.set()
                release.wait(10)
        except Exception as exc:
            errors.append(exc)
    def second():
        try:
            attempted.set()
            with scheduled_queue(name):
                second_entered.set()
        except Exception as exc:
            errors.append(exc)
    a = threading.Thread(target=first)
    b = threading.Thread(target=second)
    a.start()
    try:
        assert held.wait(5)
        b.start()
        assert attempted.wait(5)
        assert not second_entered.wait(0.2)
    finally:
        release.set()
        a.join(10)
        if b.ident is not None:
            b.join(10)
    assert not errors and second_entered.is_set()
    assert not a.is_alive() and not b.is_alive()
