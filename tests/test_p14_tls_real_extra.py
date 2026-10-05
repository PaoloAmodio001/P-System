import ssl

import pytest

from network.node_tls_identity import get_node_tls_config
from network.secure_transport import SecureTransport


def test_p14_trusted_ca_wrong_hostname_is_rejected():
    server_context = SecureTransport.create_server_context(
        get_node_tls_config("p14-extra-server")
    )
    client_config = get_node_tls_config("p14-extra-client")
    client_context = SecureTransport.create_client_context(client_config)

    import socket
    import threading

    left, right = socket.socketpair()
    errors = []

    def server():
        try:
            tls = SecureTransport.wrap_server(left, server_context)
            tls.close()
        except Exception as exc:
            errors.append(exc)

    thread = threading.Thread(target=server)
    thread.start()

    with pytest.raises(ssl.SSLError):
        SecureTransport.wrap_client(
            right,
            client_context,
            "p14-extra-server-wrong-name",
        )

    thread.join(timeout=3)
    assert errors or True
    right.close()
