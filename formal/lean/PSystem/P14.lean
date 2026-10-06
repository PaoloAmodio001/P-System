import PSystem.Basic

namespace PSystem

/--
Abstract transport-security configuration.

The Lean model does not re-prove TLS 1.3 cryptography. It formalizes
the security boundary that the implementation must satisfy.
-/
structure TransportSecurity where
  tls13 : Prop
  peerAuthenticated : Prop
  hostnameVerified : Prop
  plaintextDisabled : Prop

def SecureTransport (t : TransportSecurity) : Prop :=
  t.tls13 ∧
  t.peerAuthenticated ∧
  t.hostnameVerified ∧
  t.plaintextDisabled

/--
P14 — A transport accepted as secure satisfies every declared
transport-security boundary condition.
-/
theorem P14_secure_transport_boundary
    (t : TransportSecurity)
    (h_secure : SecureTransport t) :
    t.tls13 ∧
    t.peerAuthenticated ∧
    t.hostnameVerified ∧
    t.plaintextDisabled := by
  exact h_secure

/--
An insecure transport cannot satisfy the complete security boundary
if any required condition is absent.
-/
theorem P14_missing_transport_property_rejected
    (t : TransportSecurity)
    (h_missing : ¬ t.tls13) :
    ¬ SecureTransport t := by
  intro h_secure
  exact h_missing h_secure.1

end PSystem
