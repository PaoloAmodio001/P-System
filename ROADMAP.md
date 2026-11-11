# Roadmap

Next steps, in order. None of them is done, and none is a promise.

## Code

1. ~~Remove the historical mode~~: done, with the modules of `core/`, the tests and the benchmarks that only it used.
2. ~~Split `network/quorum.py`~~: done (`network/quorum/`: common, store, replica, driver, runtime), with no access to private
   members across them.

## Model and evidence

3. ~~Narrow the gap between the Python code and the Lean model~~: the vote lock, the execution of a certificate and the
   rounds run as compiled Lean code, with theorems that the arguments Python hands over are enough
   (`docs/PROOF-OBLIGATIONS.md`, "Python and Lean"). Still outside: the driver (buffer, resends, epochs), the store, signatures.
4. Prove what is now argued by hand: execution across epochs (today certification only), `SingleVersion` from the
   signature of the sender, and finite runs for the hypotheses on infinite chains of epochs.
5. ~~A liveness statement~~: `good_round_decides` and `honest_leader_within_n_rounds` (`QuorumRounds.lean`), under partial
   synchrony. Still to do: a split still open at the end of an epoch stays locked (`docs/PROOF-SCOPE.md`).

## Outside the code

6. External review of the protocol, the model and the code (`docs/AUDIT-PACKAGE.md`).
7. A run on separate machines (`docs/SEPARATE-MACHINES.md`), then on independent operators (`docs/VALIDATION-PLAN.md`).
