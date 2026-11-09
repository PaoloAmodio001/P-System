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


def test_load_missing_file_raises_structured_error(tmp_path):
    import pytest

    with pytest.raises(ValueError, match="KEY FILE NOT FOUND"):
        Identity.load(tmp_path / "missing.key")


def test_load_directory_raises_structured_error(tmp_path):
    import pytest

    directory = tmp_path / "dir.key"
    directory.mkdir()
    directory.chmod(0o700)
    with pytest.raises(ValueError, match="NOT A REGULAR FILE"):
        Identity.load(directory)


def test_load_symlink_to_0600_key_succeeds(tmp_path):
    # Explicit decision: stat() follows symlinks, so target permissions apply;
    # a symlink to a properly protected key is accepted.
    key = tmp_path / "id.key"
    identity = Identity.create()
    identity.save(key)
    link = tmp_path / "id.link"
    link.symlink_to(key)
    loaded = Identity.load(link)
    assert loaded.public_key == identity.public_key


def test_load_symlink_to_0644_key_is_refused(tmp_path):
    import pytest

    key = tmp_path / "id.key"
    Identity.create().save(key)
    key.chmod(0o644)
    link = tmp_path / "id.link"
    link.symlink_to(key)
    with pytest.raises(ValueError, match="READABLE BY OTHERS"):
        Identity.load(link)
