from core.identity_claim import IdentityClaim


def encode_identity_claim(
    claim: IdentityClaim,
) -> dict:
    return {
        "type": "IDENTITY_CLAIM",
        "identity_id": claim.identity_id,
        "alias": claim.alias,
        "public_key": claim.public_key.hex(),
        "signature": claim.signature.hex(),
    }


def decode_identity_claim(
    message: dict,
) -> IdentityClaim:

    if message.get("type") != "IDENTITY_CLAIM":
        raise ValueError(
            "INVALID IDENTITY CLAIM"
        )

    return IdentityClaim(
        identity_id=message["identity_id"],
        alias=message["alias"],
        public_key=bytes.fromhex(
            message["public_key"]
        ),
        signature=bytes.fromhex(
            message["signature"]
        ),
    )
