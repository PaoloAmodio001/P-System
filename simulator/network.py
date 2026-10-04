from core.state import State
from core.event import Transfer
from network.node import Node


def create_network(count: int, initial_state: State) -> list[Node]:
    return [
        Node(f"node-{i+1}", initial_state.copy())
        for i in range(count)
    ]


def broadcast(nodes: list[Node], tx: Transfer) -> dict[str, bool]:
    return {
        node.node_id: node.receive(tx)
        for node in nodes
    }


def roots(nodes: list[Node]) -> dict[str, str]:
    return {
        node.node_id: node.state_root()
        for node in nodes
    }


if __name__ == "__main__":
    nodes = create_network(
        5,
        State({"alice": 10})
    )

    tx = Transfer("alice", "bob", 3, 0)

    results = broadcast(nodes, tx)

    print("TRANSACTION:", tx)
    print("RESULTS:", results)
    print("\nSTATE ROOTS:")

    for node_id, root in roots(nodes).items():
        print(f"  {node_id}: {root}")
