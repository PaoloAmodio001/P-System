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


def test_load_refuses_key_file_readable_by_others(tmp_path):
    import pytest

    key = tmp_path / "id.key"
    Identity.create().save(key)
    key.chmod(0o644)
    with pytest.raises(ValueError, match="READABLE BY OTHERS"):
        Identity.load(key)
    with pytest.raises(ValueError, match="chmod 600"):
        Identity.load(key)
