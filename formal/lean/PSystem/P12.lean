import PSystem.P08

namespace PSystem

/--
Pending evidence may be promoted only after authorization.
-/
def PromotionAuthorized
    (e : SignedEvidence)
    (a : IdentityAuthorization) : Prop :=
  Authorized e a

/--
Promotion is modelled as a guarded state transition.
Unauthorized pending evidence leaves the state unchanged.
-/
noncomputable def Promote
    (s : State)
    (authorized : Prop)
    (next : State) : State := by
  classical
  exact if authorized then next else s

/--
P12 — Reconciliation cannot bypass the authorization gate.
-/
theorem P12_unauthorized_promotion_preserves_state
    (s : State)
    (e : SignedEvidence)
    (a : IdentityAuthorization)
    (next : State)
    (h_unauthorized : ¬ PromotionAuthorized e a) :
    Promote s (PromotionAuthorized e a) next = s := by
  classical
  simp [Promote, h_unauthorized]

/--
Authorized pending evidence may cross the promotion boundary.
-/
theorem P12_authorized_promotion_applies
    (s : State)
    (e : SignedEvidence)
    (a : IdentityAuthorization)
    (next : State)
    (h_authorized : PromotionAuthorized e a) :
    Promote s (PromotionAuthorized e a) next = next := by
  classical
  simp [Promote, h_authorized]

end PSystem
