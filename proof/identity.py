"""Identity lifecycle proof obligations."""
def identity_execution_gate(node, signed_event):
    """True only when a signed event has a valid identity authorization."""
    claim = node.identities.get(signed_event.identity_id)
    return claim is not None and node._verify_signed_identity(signed_event)


def pending_is_non_executable(node, signed_event):
    if signed_event.identity_id in node.identities:
        return True
    return signed_event.transfer not in node.events and signed_event.transfer not in node.local_events
