import PSystem.Basic

namespace PSystem

/--
An event is causally executable when every declared parent
has a corresponding executable event in the supplied knowledge.
-/
def ParentsExecutable
    (s : State)
    (e : Event)
    (knowledge : List Event) : Prop :=
  ∀ parentId, parentId ∈ e.parents →
    ∃ parent, parent ∈ knowledge ∧
      parent.id = parentId ∧
      Executable s parent

/--
P02 — Every declared causal parent required for execution
must itself be executable.
-/
theorem P02_causal_dependencies_preserved
    (s : State)
    (e : Event)
    (knowledge : List Event)
    (h : ParentsExecutable s e knowledge) :
    ∀ parentId, parentId ∈ e.parents →
      ∃ parent, parent ∈ knowledge ∧
        parent.id = parentId ∧
        Executable s parent := by
  exact h

/--
Direct parenthood implies causal precedence.
-/
theorem P02_direct_parent_is_causal
    (parent child : Event)
    (h : DirectParent parent child) :
    CausalBefore parent child := by
  exact direct_parent_is_causal parent child h

/--
Causal precedence is transitive.
-/
theorem P02_causal_transitivity
    (a b c : Event)
    (hab : CausalBefore a b)
    (hbc : CausalBefore b c) :
    CausalBefore a c := by
  exact causal_before_transitive a b c hab hbc

end PSystem
