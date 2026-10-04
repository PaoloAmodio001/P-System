from core.event import Transfer
from core.state import State


def verify_transfer(state: State, tx: Transfer) -> bool:
    if tx.amount <= 0:
        return False

    if tx.sender == tx.receiver:
        return False

    if tx.nonce != state.nonce(tx.sender):
        return False

    if state.balance(tx.sender) < tx.amount:
        return False

    return True


def apply_transfer(state: State, tx: Transfer) -> State:
    if not verify_transfer(state, tx):
        raise ValueError("INVALID TRANSFER")

    new_state = state.copy()

    new_state.balances[tx.sender] -= tx.amount

    new_state.balances[tx.receiver] = (
        new_state.balances.get(tx.receiver, 0)
        + tx.amount
    )

    new_state.nonces[tx.sender] = (
        new_state.nonce(tx.sender) + 1
    )

    return new_state
