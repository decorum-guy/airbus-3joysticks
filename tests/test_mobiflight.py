from airbus3j.mobiflight import MobiFlightTransport


class FakeSC:
    def __init__(self):
        self.receive_calls = 0

    def receive(self, timeout_seconds=None):
        self.receive_calls += 1
        return False


class HandshakeTransport(MobiFlightTransport):
    def __init__(self, sc, pong=True):
        super().__init__(sc)
        self.commands = []
        self.pong = pong

    def _map_areas(self):
        return None

    def send_command(self, command):
        self.commands.append(command)
        if self.pong and len(self.commands) >= 2 and command == "MF.Ping":
            self.responses.append("MF.Pong")
            self.last_response = "MF.Pong"
        return True


def test_handshake_primes_then_requires_pong():
    transport = HandshakeTransport(FakeSC(), pong=True)
    assert transport.initialize(timeout_seconds=0.2) is True
    assert transport.available is True
    assert transport.commands[:2] == ["MF.Ping", "MF.Ping"]


def test_handshake_timeout_is_not_reported_available():
    transport = HandshakeTransport(FakeSC(), pong=False)
    assert transport.initialize(timeout_seconds=0.2) is False
    assert transport.available is False
    assert "MF.Pong timeout" in str(transport.last_error)


def test_execute_rpn_uses_mobiflight_simvars_set_protocol():
    transport = HandshakeTransport(FakeSC(), pong=True)
    assert transport.initialize(timeout_seconds=0.2)
    assert transport.execute_rpn("(>H:A320_Neo_FCU_SPEED_PUSH)") is True
    assert transport.commands[-1] == "MF.SimVars.Set.(>H:A320_Neo_FCU_SPEED_PUSH)"


def test_execute_rpn_refuses_when_transport_is_offline():
    transport = HandshakeTransport(FakeSC(), pong=False)
    assert transport.execute_rpn("(>H:ANYTHING)") is False
    assert "not available" in str(transport.last_error)


def test_command_length_limit_is_enforced_before_simconnect_call():
    transport = MobiFlightTransport(FakeSC())
    try:
        transport.send_command("x" * transport.STRING_SIZE)
    except ValueError as exc:
        assert "shorter than" in str(exc)
    else:
        raise AssertionError("expected ValueError")
