from crypto.identity import Identity, verify_signature


def test_valid_signature():

    identity = Identity.create()

    data = b"X SYSTEM EVENT"

    signature = identity.sign(data)

    assert verify_signature(
        identity.public_key,
        signature,
        data,
    )


def test_modified_data_rejected():

    identity = Identity.create()

    data = b"X SYSTEM EVENT"
    modified = b"X SYSTEM ATTACK"

    signature = identity.sign(data)

    assert not verify_signature(
        identity.public_key,
        signature,
        modified,
    )


def test_wrong_key_rejected():

    identity_a = Identity.create()
    identity_b = Identity.create()

    data = b"X SYSTEM EVENT"

    signature = identity_a.sign(data)

    assert not verify_signature(
        identity_b.public_key,
        signature,
        data,
    )
