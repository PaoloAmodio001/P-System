# Roadmap

Next steps, in order. None of them is done, and none is a promise.

## Code

1. **Remove the historical mode** (`Node(quorum=None)`) and the modules of `core/` that only it uses. It has no Byzantine
   guarantee, `psystem` never deploys it, and most of `core/` exists for it. The tests and documents that depend on it go
   with it.
2. **Split `network/quorum.py`** into store, replica, driver and configuration, and remove the accesses to private members
   across them (`_initial_state`, `StateDeriver._apply_one`, `StateDeriver._execution_failure`).

## Model and evidence

3. Narrow the gap between the Python code and the Lean model, which today is covered by differential tests only.
4. Prove what is now argued by hand: execution across epochs (today certification only), `SingleVersion` from the
   signature of the sender, and finite runs for the hypotheses on infinite chains of epochs.
5. A liveness statement that models who gathers the votes, under a network model with fairness.

## Outside the code

6. External review of the protocol, the model and the code (`docs/AUDIT-PACKAGE.md`).
7. A run on separate machines (`docs/SEPARATE-MACHINES.md`), then on independent operators (`docs/VALIDATION-PLAN.md`).
