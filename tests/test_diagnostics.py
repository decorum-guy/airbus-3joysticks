from airbus3j.diagnostics import ACTIVE_PROBES, _identity_comparison


def identity(**overrides):
    value = {
        "device_key": "serial:abc",
        "name": "Wireless Controller",
        "serial": "SERIAL-1",
        "path": "USB#PATH-1",
        "guid": "guid-1",
        "vendor_id": 0x054C,
        "product_id": 0x0CE6,
    }
    value.update(overrides)
    return value


def test_identity_prefers_real_serial_stability():
    before = identity()
    after = identity(path="USB#PATH-CHANGED")
    result = _identity_comparison(before, after)
    assert result["verdict"] == "stable_serial"
    assert result["serial_same"] is True


def test_identity_accepts_stable_path_when_serial_is_unavailable():
    before = identity(serial=None, device_key="path:abc")
    after = identity(serial=None, device_key="path:abc")
    result = _identity_comparison(before, after)
    assert result["verdict"] == "stable_path"
    assert result["path_same"] is True


def test_identity_reports_changed_fallback_instead_of_claiming_stability():
    before = identity(serial=None, path=None, device_key="fallback:one")
    after = identity(serial=None, path=None, device_key="fallback:two")
    result = _identity_comparison(before, after)
    assert result["verdict"] == "identity_changed_or_unresolved"
    assert result["same_model"] is True


def test_every_active_probe_has_explicit_inverse_restore_event():
    assert ACTIVE_PROBES
    for probe in ACTIVE_PROBES:
        assert probe["event"]
        assert probe["restore_event"]
        assert probe["event"] != probe["restore_event"]
        assert probe["simvar"]
