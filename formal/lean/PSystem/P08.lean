import PSystem.P07

namespace PSystem

/--
Identity authorization state.

The signer identity and the identity claim must refer to the same
cryptographic identity before execution is authorized.
-/
structure IdentityAuthorization where
  signerIdentity : Identity
  claimedIdentity : Identity
  deriving DecidableEq, Repr

/--
Identity binding is equality of the cryptographic identity roots.
-/
def IdentityBound (a : IdentityAuthorization) : Prop :=
  a.signerIdentity = a.claimedIdentity

/--
Execution authorization requires both authenticated evidence and
a valid identity binding.
-/
def Authorized
    (e : SignedEvidence)
    (a : IdentityAuthorization) : Prop :=
  SignatureValid e ∧ IdentityBound a

/--
P08 — A valid signature alone is insufficient without identity binding.
-/
theorem P08_signature_without_identity_binding_not_authorized
    (e : SignedEvidence)
    (a : IdentityAuthorization)
    (_h_signature : SignatureValid e)
    (h_not_bound : ¬ IdentityBound a) :
    ¬ Authorized e a := by
  intro h_authorized
  exact h_not_bound h_authorized.2

/--
A fully authorized event necessarily satisfies both gates.
-/
theorem P08_authorized_implies_identity_binding
    (e : SignedEvidence)
    (a : IdentityAuthorization)
    (h_authorized : Authorized e a) :
    IdentityBound a := by
  exact h_authorized.2

end PSystem
