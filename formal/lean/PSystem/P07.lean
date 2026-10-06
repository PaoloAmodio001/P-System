import PSystem.Basic

namespace PSystem

/--
Abstract signed evidence.

The formal model records the payload authenticated by the signature
and the payload actually presented for verification.
-/
structure SignedEvidence where
  signedPayload : String
  presentedPayload : String
  deriving DecidableEq, Repr

/--
A signature is valid only when it authenticates exactly the payload
that is presented.
-/
def SignatureValid (e : SignedEvidence) : Prop :=
  e.signedPayload = e.presentedPayload

/--
P07 — Authenticity rejects payload mutation.

If the presented payload differs from the payload covered by the
signature, the evidence cannot be valid.
-/
theorem P07_tampered_payload_rejected
    (e : SignedEvidence)
    (h_tampered : e.signedPayload ≠ e.presentedPayload) :
    ¬ SignatureValid e := by
  intro h_valid
  exact h_tampered h_valid

/--
A valid signature implies exact payload binding.
-/
theorem P07_valid_signature_binds_payload
    (e : SignedEvidence)
    (h_valid : SignatureValid e) :
    e.signedPayload = e.presentedPayload := by
  exact h_valid

end PSystem
