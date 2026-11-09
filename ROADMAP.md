# Roadmap

Next steps, in order. None of them is done, and none is a promise.

## Code

1. **Remove the historical mode** (`Node(quorum=None)`) and the modules of `core/` that only it uses. It has no Byzantine
   guarantee, `psystem` never deploys it, and most of `core/` exists for it. The tests and documents that depend on it go
   with it.
2. **Split `network/quorum.py`** into store, replica, driver and configuration, and remove the accesses to private members
   across them (`_initial_state`, `StateDeriver._apply_one`, `StateDeriver._execution_failure`).
3. **Cost of `SNAPSHOT_REQUEST`.** A member derives the requested state from its log for each request, with no cache and
   no cost charged to the peer. A peer with a certificate can make a member repeat that work.

## Model and evidence

4. Narrow the gap between the Python code and the Lean model, which today is covered by differential tests only.
5. Prove what is now argued by hand: execution across epochs (today certification only), `SingleVersion` from the
   signature of the sender, and finite runs for the hypotheses on infinite chains of epochs.
6. A liveness statement that models who gathers the votes, under a network model with fairness.

## Outside the code

7. External review of the protocol, the model and the code (`docs/AUDIT-PACKAGE.md`).
8. A run on separate machines (`docs/SEPARATE-MACHINES.md`), then on independent operators (`docs/VALIDATION-PLAN.md`).
