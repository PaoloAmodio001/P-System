import PSystem.Derive

namespace PSystem.Quorum

/-!
# Byzantine quorum model (obligation O7)

The protocol of an honest node, in the style of FastPay: a validator signs
at most one event per `(sender, nonce)`, and a node executes an event only
with a certificate signed by a quorum. This module has only definitions; the
results are in `QuorumSafety` and `QuorumDerive`.

The adversary is not a part of the model but a quantifier. A run gives each
node its own arbitrary list of inputs (`Fin n → List Input`), and results
are meant to hold for every such choice: messages may be delayed, lost,
duplicated, forged in content, or different for each node. Faulty nodes
have no state and no transitions. Whatever they sign can appear in a
certificate; `Unforgeable` limits only what honest validators appear to
have signed.

An input the node refuses leaves its state unchanged, so retrying is just
delivering the same input again. A Python node with a buffer of pending
certificates corresponds to a particular list of inputs.

Differences from the planned Python implementation, to be stated wherever
results are used:

- Signatures are abstract: `Sig` and `verify` are parameters. Nothing is
  proved about Ed25519. Python will sign a domain-separated encoding of
  the event.
- Event ids are `Nat`, with no relation to the content of the event. Ids
  are SHA-256 hashes in Python. `voteAllowed` also locks on the id, so that
  distinct certified events with one id need no collision-resistance
  hypothesis.
- `parents` is a list here; Python's canonical form sorts it.
- The vote does not check the balance. Python may refuse more votes than
  this model does; that only removes behaviours.
- Votes are never lost. A node that restarts without its votes has to be
  counted among the faulty ones.
-/

/-- An event with signatures attributed to validators. Nothing about a value
of this type is valid until `certValid` checks it. -/
structure Cert (n : Nat) (Sig : Type) where
  event : Event
  sigs  : List (Fin n × Sig)

/-- What a node can receive. Any value can be delivered to any node. -/
inductive Input (n : Nat) (Sig : Type) where
  | voteRequest (e : Event)
  | certificate (c : Cert n Sig)

/-- Local state of an honest node. -/
structure NodeState (n : Nat) (Sig : Type) where
  /-- Events this node has signed as a validator, latest first. -/
  votes : List Event
  /-- State reached by the executed events. -/
  state : State
  /-- Executed certificates, in execution order. -/
  log   : List (Cert n Sig)

/-- Events executed by a node, in execution order. -/
def NodeState.executed {n Sig} (st : NodeState n Sig) : List Event :=
  st.log.map Cert.event

/--
The vote lock. A validator may sign `e` unless it has already signed a
different event with the same `(sender, nonce)` or the same id. Signing the
same event again is allowed.
-/
def voteAllowed (votes : List Event) (e : Event) : Bool :=
  votes.all fun e' =>
    e' == e || (!(e'.sender == e.sender && e'.nonce == e.nonce) && e'.id != e.id)

/--
A valid certificate: signers are pairwise distinct, there are at least `q`
of them and every signature verifies. Signers are `Fin n`, so non-members
cannot appear.
-/
def certValid {n Sig} (verify : Fin n → Event → Sig → Bool) (q : Nat)
    (c : Cert n Sig) : Bool :=
  decide (c.sigs.map Prod.fst).Nodup && decide (q ≤ c.sigs.length) &&
    c.sigs.all fun p => verify p.1 c.event p.2

/--
One transition of an honest node. `auth` is the node's own check of the
sender's authorization, and it can differ between nodes: in Python it
depends on locally registered identity claims.

A certificate is executed only if it is valid and its event is executable
on the current state, causally ready and not already executed by id: the
same conditions as `derive`, plus the certificate.
-/
def step {n Sig} (verify : Fin n → Event → Sig → Bool) (q : Nat) (auth : Event → Bool)
    (st : NodeState n Sig) : Input n Sig → NodeState n Sig
  | .voteRequest e =>
      if auth e && voteAllowed st.votes e
      then { st with votes := e :: st.votes } else st
  | .certificate c =>
      let ids := st.executed.map Event.id
      if certValid verify q c && executableBool st.state c.event &&
          r17ReadyBool ids c.event && !ids.contains c.event.id
      then { st with state := ApplyEvent st.state c.event, log := st.log ++ [c] }
      else st

/-- An honest node that starts from `s₀` and processes its inputs in order. -/
def runNode {n Sig} (verify : Fin n → Event → Sig → Bool) (q : Nat) (auth : Event → Bool)
    (s₀ : State) (inputs : List (Input n Sig)) : NodeState n Sig :=
  inputs.foldl (step verify q auth) { votes := [], state := s₀, log := [] }

/--
Signatures cannot be forged, for one run: if a certificate delivered to an
honest node carries a valid signature of an honest validator on an event,
that validator really voted for that event in this run.

This is an assumption about the run, to be stated as a hypothesis of each
theorem that needs it. It says nothing about conflicts, about faulty
signers or about the inputs of faulty nodes. It does not require the vote
to come before the signature is used, which makes it weaker than what a
signature scheme gives.
-/
def Unforgeable {n Sig} (verify : Fin n → Event → Sig → Bool) (faulty : List (Fin n))
    (q : Nat) (auth : Fin n → Event → Bool) (s₀ : State)
    (inputs : Fin n → List (Input n Sig)) : Prop :=
  ∀ u, u ∉ faulty → ∀ c, Input.certificate c ∈ inputs u →
    ∀ p, p ∈ c.sigs → p.1 ∉ faulty → verify p.1 c.event p.2 = true →
      c.event ∈ (runNode verify q (auth p.1) s₀ (inputs p.1)).votes

end PSystem.Quorum
