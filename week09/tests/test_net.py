import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))
import net

def test_circuit_breaker_trips_then_fast_fails():
    net._CONSEC_FAIL[0] = 0
    net._BLOCK.clear()
    for _ in range(net.CIRCUIT_THRESHOLD):
        net._note_failure()
    assert net._BLOCK.is_set()
    import pytest
    with pytest.raises(RuntimeError):
        net._request("GET", "https://example.invalid")

def test_success_resets_counter():
    net._BLOCK.clear(); net._CONSEC_FAIL[0] = 5
    net._note_success()
    assert net._CONSEC_FAIL[0] == 0

def test_retry_after_parses_seconds():
    class R: headers = {"Retry-After": "12"}
    assert net._retry_after(R()) == 12.0
    class R2: headers = {}
    assert net._retry_after(R2()) is None
