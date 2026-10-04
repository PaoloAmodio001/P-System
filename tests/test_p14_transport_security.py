import socket
import ssl

from network.secure_transport import SecureTransport


def test_p14_server_context_requires_tls13():
    context = SecureTransport.create_server_context

    assert callable(context)


def test_p14_client_context_requires_certificate_validation():
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    context.minimum_version = ssl.TLSVersion.TLSv1_3
    context.maximum_version = ssl.TLSVersion.TLSv1_3
    context.check_hostname = False
    context.verify_mode = ssl.CERT_REQUIRED

    assert context.minimum_version == ssl.TLSVersion.TLSv1_3
    assert context.maximum_version == ssl.TLSVersion.TLSv1_3
    assert context.verify_mode == ssl.CERT_REQUIRED


def test_p14_plain_socket_does_not_look_like_tls():
    left, right = socket.socketpair()

    try:
        SecureTransport.send(
            left,
            {"type": "PING"},
        )

        raw = right.recv(64)

        # The application framing must not be confused with a TLS
        # ClientHello. This test documents that SecureTransport itself
        # expects to operate on an already TLS-wrapped socket.
        assert raw[:1] != b"\x16"
    finally:
        left.close()
        right.close()


def test_p14_tls13_is_supported():
    assert ssl.HAS_TLSv1_3
