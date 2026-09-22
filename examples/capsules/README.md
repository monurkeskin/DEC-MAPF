# Complete small experiment capsules

Run a bounded study, retain every outcome and inspect its exported evidence. Both capsules use existing solvers and teaching scenarios; neither establishes an article result.

| Capsule | Question | Bound and output |
| --- | --- | --- |
| [Negotiation](negotiation/README.md) | How does a recorded agreement relate to later movement? | 4 trials; checked bundles, offline replay and a narrated session |
| [Four settings](settings/README.md) | How do goal/wait rules enter an experiment? | 16 trials; CBS/Prioritized, all four settings, canonical outcome cards |

Each directory is portable with an installed core wheel. Use a fresh output directory, one worker and the declared 120-second study budget. Failures and timeouts remain in `all-trials.json`; the runner does not retry them or substitute a successful example. The [negotiation walkthrough](../../docs/NEGOTIATION-WALKTHROUGH.md) explains a real saved teaching trace.

Next: [create your own study](../../docs/NEW-STUDY.md) and change its explicit population before making a scientific claim.
