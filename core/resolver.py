from core.event import Transfer, event_payload


class ConflictResolver:

    @staticmethod
    def conflicting(a: Transfer, b: Transfer) -> bool:
        """
        Two transfers conflict when they attempt to spend
        the same sender state at the same nonce.
        """

        id_a = a.event_id()
        id_b = b.event_id()

        payload_a = event_payload(a)
        payload_b = event_payload(b)

        if id_a == id_b and payload_a != payload_b:
            raise ValueError("DUPLICATE EVENT ID WITH DIFFERENT CONTENT")

        if a.sender != b.sender:
            return False

        if a.nonce != b.nonce:
            return False

        return id_a != id_b

    @staticmethod
    def compatible(events: list[Transfer]) -> bool:
        # Mantiene il controllo d'integrità degli ID anche per input
        # contenenti eventi duplicati o oggetti non canonici.
        payload_by_id = {}
        event_by_sender_nonce = {}

        for event in events:
            event_id = event.event_id()
            payload = event_payload(event)

            previous_payload = payload_by_id.get(event_id)
            if previous_payload is not None and previous_payload != payload:
                raise ValueError(
                    "DUPLICATE EVENT ID WITH DIFFERENT CONTENT"
                )
            payload_by_id[event_id] = payload

            key = (event.sender, event.nonce)
            previous_id = event_by_sender_nonce.get(key)

            if previous_id is not None and previous_id != event_id:
                return False

            event_by_sender_nonce[key] = event_id

        return True
