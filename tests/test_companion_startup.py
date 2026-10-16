import errno

import pytest

from principia_asd.web import server


def test_occupied_port_explains_how_to_recover(monkeypatch):
    def occupied(*args):
        raise OSError(errno.EADDRINUSE, 'address in use')

    monkeypatch.setattr(server, 'ThreadingHTTPServer', occupied)
    with pytest.raises(SystemExit, match='Port 8150 is already in use') as caught:
        server._listen(object, 8150)
    assert '--port 8152' in str(caught.value)
    assert 'http://127.0.0.1:8150/' in str(caught.value)


@pytest.mark.parametrize('port', [0, -1, 65536])
def test_invalid_local_port_rejected(port):
    with pytest.raises(SystemExit, match='between 1 and 65535'):
        server._listen(object, port)


def test_companion_keeps_loopback_binding(monkeypatch):
    observed = []
    monkeypatch.setattr(server, 'ThreadingHTTPServer', lambda address, handler: observed.append(address))
    server._listen(object, 8154)
    assert observed == [('127.0.0.1', 8154)]
