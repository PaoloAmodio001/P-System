from core.global_proof import GlobalStateProof


def distinguish(a: GlobalStateProof, b: GlobalStateProof) -> bool:
    """
    Returns True only if the available proof material
    contains an intrinsic difference that can distinguish
    the two states.

    This deliberately does NOT use:
    - node majority
    - timestamps
    - chain length
    - proof of work
    - stake
    - external authority
    """

    if a.state_root == b.state_root:
        return False

    if a.events == b.events:
        return False

    return False
