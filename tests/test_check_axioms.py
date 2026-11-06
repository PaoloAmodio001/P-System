"""The check on axioms in continuous integration must pass on wrapped lines, and fail on what is wrong."""

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SPEC = importlib.util.spec_from_file_location("check_axioms", ROOT / "scripts" / "check_axioms.py")
check = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(check)

# As Lean really prints it: this one failed PR #3.
WRAPPED = """'PSystem.Quorum.attestation_without_honest_signer_proves_nothing' depends on axioms: [propext,
 Classical.choice,
 Quot.sound]
'PSystem.sumBy_nil' does not depend on any axioms
'PSystem.b' depends on axioms: [propext]
"""


def test_a_list_on_several_lines_is_read_whole():
    assert check.axioms_of(WRAPPED)["PSystem.Quorum.attestation_without_honest_signer_proves_nothing"] == {
        "propext",
        "Classical.choice",
        "Quot.sound",
    }
    assert check.problems(WRAPPED, 3) == []


def test_another_axiom_is_refused_also_in_a_wrapped_list():
    log = WRAPPED.replace(" Quot.sound]", " sorryAx]")
    assert "sorryAx" in check.problems(log, 3)[0]


def test_a_theorem_with_no_answer_is_refused():
    assert check.problems(WRAPPED, 4) == ["4 THEOREMS ASKED, 3 ANSWERED"]


def test_the_step_of_continuous_integration_uses_this_check():
    workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text()
    assert "scripts/check_axioms.py audit.log" in workflow
    assert "grep 'depends on axioms'" not in workflow
