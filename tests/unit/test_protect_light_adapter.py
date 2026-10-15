import importlib.util
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest

PATH = (
    Path(__file__).resolve().parents[2]
    / "deployment/protect-mcp/protect_light_adapter.py"
)
spec = importlib.util.spec_from_file_location("protect_light_adapter", PATH)
m = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = m
spec.loader.exec_module(m)
CAMERA = "6797d43f03968103e40003f1"


def stamp(t):
    return datetime.fromtimestamp(t, UTC).isoformat()


def event(t=101, identity="event-1", **kw):
    return dict(
        id=identity,
        camera=CAMERA,
        type="smartDetectZone",
        smart_detect_types=["person"],
        start=stamp(t),
        **kw,
    )


def envelope(*events):
    return {"success": True, "data": {"detections": list(events), "count": len(events)}}


def ready():
    gate = m.Admission(CAMERA)
    assert gate.select(envelope(event(99)), 100, 10) == []
    return gate


def test_new_person_keeps_original_identity_and_time():
    out = ready().select(envelope(event()), 102, 12)
    assert out == [
        {"event_id": "event-1", "source_id": CAMERA, "occurred_at": stamp(101)}
    ]


def test_duplicates_and_changed_same_id_do_not_extend():
    gate = ready()
    assert len(gate.select(envelope(event()), 102, 12)) == 1
    assert gate.select(envelope(event(103)), 104, 14) == []


@pytest.mark.parametrize(
    "field,value",
    [
        ("camera", "other"),
        ("type", "motion"),
        ("smart_detect_types", ["vehicle"]),
        ("start", "bad"),
        ("start", "1970-01-01T00:01:41"),
        ("id", "../bad"),
    ],
)
def test_reject_wrong_or_malformed_detection(field, value):
    item = event()
    item[field] = value
    assert ready().select(envelope(item), 102, 12) == []


@pytest.mark.parametrize("t", [99, 100, 103, 40])
def test_reject_boundary_old_and_future(t):
    assert ready().select(envelope(event(t)), 102, 12) == []


def test_reconnect_discards_gap_events():
    gate = ready()
    gate.disconnect()
    assert gate.select(envelope(event(103)), 104, 14) == []
    assert len(gate.select(envelope(event(105)), 106, 16)) == 1


def test_clock_jump_and_long_poll_gap_rearm_without_delivery():
    for wall, mono in [(110, 12), (100, 12), (140, 50)]:
        assert ready().select(envelope(event(wall - 1)), wall, mono) == []


@pytest.mark.parametrize(
    "payload",
    [
        {"success": False},
        {"success": True, "data": {}},
        {"success": True, "data": {"detections": [], "count": 1}},
        envelope(*[event(101, str(n)) for n in range(100)]),
    ],
)
def test_bad_or_full_page_disarms(payload):
    gate = ready()
    with pytest.raises(ValueError):
        gate.select(payload, 102, 12)
    assert gate.select(envelope(event(103)), 104, 14) == []


def test_configuration_refuses_unsafe_destinations_and_unused_secrets():
    base = {
        "camera_id": CAMERA,
        "launcher": "/bin/true",
        "mode": "forward",
        "endpoint": "http://pi/api/v1/lights/events/unifi",
        "token_file": "/private",
    }
    with pytest.raises(ValueError):
        m.Config.parse(base)
    for url in [
        "https://pi/other",
        "https://user:pass@pi/api/v1/lights/events/unifi",
        "https://pi/api/v1/lights/events/unifi?secret=x",
    ]:
        with pytest.raises(ValueError):
            m.Config.parse(dict(base, endpoint=url))
    with pytest.raises(ValueError):
        m.Config.parse(dict(base, mode="observe"))


def test_no_redirects():
    with pytest.raises(ValueError):
        m.NoRedirect().redirect_request(None, None, 302, "", {}, "https://other")


def test_private_file_permissions(tmp_path):
    p = tmp_path / "token"
    p.write_text("x" * 32)
    p.chmod(0o644)
    with pytest.raises(ValueError):
        m.private_read(p)
    p.chmod(0o600)
    assert m.private_read(p) == "x" * 32
    link = tmp_path / "link"
    link.symlink_to(p)
    with pytest.raises(ValueError):
        m.private_read(link)


def test_delivery_failure_does_not_retry_batch(monkeypatch):
    import asyncio
    from types import SimpleNamespace

    class Session:
        async def call_tool(self, name, arguments):
            return SimpleNamespace(
                is_error=False,
                structured_content=envelope(event(101), event(101.5, "event-2")),
                content=[],
            )

    class BrokenSink:
        calls = 0

        def send(self, item):
            self.calls += 1
            raise TimeoutError()

    gate = ready()
    sink = BrokenSink()
    monkeypatch.setattr(m.time, "time", lambda: 102)
    monkeypatch.setattr(m.time, "monotonic", lambda: 12)
    with pytest.raises(TimeoutError):
        asyncio.run(m.poll(Session(), gate, sink))
    assert sink.calls == 1
    assert gate.last is None


def test_observe_never_sends(monkeypatch, capsys):
    import asyncio
    from types import SimpleNamespace

    class Session:
        async def call_tool(self, name, arguments):
            assert name == "protect_execute"
            assert arguments["arguments"]["camera_id"] == CAMERA
            assert arguments["arguments"]["detection_type"] == "person"
            return SimpleNamespace(
                is_error=False, structured_content=envelope(event()), content=[]
            )

    monkeypatch.setattr(m.time, "time", lambda: 102)
    monkeypatch.setattr(m.time, "monotonic", lambda: 12)
    asyncio.run(m.poll(Session(), ready(), None))
    output = capsys.readouterr().out
    assert '"observed": 1' in output
    assert CAMERA not in output
    assert "event-1" not in output


def test_sink_acceptance_and_inhibition_use_same_original_event(tmp_path, monkeypatch):
    import json

    token = tmp_path / "token"
    token.write_text("x" * 40)
    token.chmod(0o600)
    config = m.Config.parse(
        {
            "camera_id": CAMERA,
            "launcher": "/bin/true",
            "mode": "forward",
            "endpoint": "https://pi/api/v1/lights/events/unifi",
            "token_file": str(token),
        }
    )
    sink = m.Sink(config)
    request_body = {
        "event_id": "event-1",
        "source_id": CAMERA,
        "occurred_at": stamp(101),
    }
    monkeypatch.setattr(m.time, "time", lambda: 102)

    class Response:
        status = 200
        accepted = False
        duplicate = False

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def read(self, count):
            return json.dumps(
                {
                    "accepted": self.accepted,
                    "duplicate": self.duplicate,
                    "status": {"mode": "MANUAL_OFF"},
                }
            ).encode()

    class Opener:
        def open(self, request, timeout):
            assert json.loads(request.data) == request_body
            assert timeout == 5
            return Response()

    sink.opener = Opener()
    assert sink.send(request_body) == "inhibited"
    Response.accepted = True
    assert sink.send(request_body) == "accepted"
    Response.duplicate = True
    assert sink.send(request_body) == "duplicate"


def test_unpack_rejects_errors_and_oversize():
    from types import SimpleNamespace

    with pytest.raises(ValueError):
        m.unpack(SimpleNamespace(is_error=True))
    with pytest.raises(ValueError):
        m.unpack(
            SimpleNamespace(
                is_error=False,
                structured_content=None,
                content=[SimpleNamespace(type="text", text="x" * 131073)],
            )
        )


def test_oversized_structured_reply_is_rejected():
    from types import SimpleNamespace

    with pytest.raises(ValueError):
        m.unpack(
            SimpleNamespace(is_error=False, structured_content={"pad": "x" * 131073})
        )


def test_total_deadline_interrupts_trickle_and_clears_timer():
    import signal
    import time

    def trickle():
        while True:
            time.sleep(0.01)

    before = time.monotonic()
    with pytest.raises(TimeoutError), m.delivery_deadline(0.05):
        trickle()
    assert time.monotonic() - before < 1
    assert signal.getitimer(signal.ITIMER_REAL) == (0.0, 0.0)
