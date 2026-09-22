# Centralized solver and article comparison contract

All four physical settings apply to built-in Python solvers and independent output validation:

| Setting | Wait before arrival | Occupancy after arrival |
| --- | --- | --- |
| 1 | Forbidden | Park |
| 2 | Allowed | Park |
| 3 | Forbidden | Disappear after the arrival tick |
| 4 | Allowed | Disappear after the arrival tick |

The modern contract treats the first goal arrival as absorbing. The published decentralized lifecycle is consistent with that choice. Some archived centralized paths visit a goal, leave, and later finish there; those paths do not satisfy this modern contract. Their exclusion does not establish that they violate every MAPF definition. A paper comparison must disclose this difference instead of silently changing the validator to improve a score.

## Python solvers

`CBS` is a bounded implementation. The registry identifier `EECBS` resolves to **SimplifiedFocalCBS**, not the published C++ EECBS algorithm. It has no certified EECBS suboptimality guarantee. Its internal costs and focal threshold count actions, including waits; counting path vertices would add one per agent and incorrectly widen a multiplicative threshold. Prioritized Planning is an incomplete, order-dependent baseline, not an optimal oracle.

Search exhaustion, a low-level horizon/expansion limit, a high-level iteration limit, and wall timeout have separate termination reasons. A failed search without a complete candidate is `not_checked`; a claimed complete solution still undergoes independent path validation. Increasing the process timeout to 600 seconds does not remove search or step bounds. Report all effective bounds. Application jobs always use the explicitly frozen timeout; direct solver callers may use the constructor fallback.

The small exhaustive oracle suite covers 48 two-agent instances under the four settings for each of CBS, focal weight 1, focal weight 1.1 and Prioritized Planning (192 executions). It independently checks joint physical trajectories and checks optimal cost for CBS/focal weight 1 on those fixtures. It does not prove general optimality or fidelity to historical external binaries.

## External adapters

Each binary must declare its family, supported physical setting(s), coordinate convention and preferably an expected SHA-256. EECBS receives `--suboptimality`; CBSH2-RTC does not support that argument in its upstream driver. The article CBSH2-RTC profile exposes settings 1/2 only. The historical runner used separate executables for wait and disappearance variants; changing a label or timeout does not reproduce those variants.

Use a single declared setting for a specialized binary. A binary supporting multiple settings must provide explicit `setting_arguments` for each. Those arguments cannot override the scenario, output, cutoff or weight. Standard upstream drivers do not supply generic wait/disappearance switches; do not invent flags. A declaration or mapping is configuration, not evidence of correct behavior.

The parser accepts coordinate pairs and row-major linear cell IDs, preserves the scenario roster order, and rejects malformed/duplicate/missing trajectories through strict parsing and independent validation. Process cutoff and invocation provenance are retained.

Before admitting a real binary as a paper baseline, freeze its source revision, source patches, compiler/build options, executable hash, setting/weight mapping and a small independent-oracle qualification receipt. Parser fixtures are not real-binary qualification. Archived validated paths may be used only with their separate historical provenance and any independent optimality certificate; they are not fresh 600-second runs.

The [native build and qualification workflow](NATIVE-BASELINES.md) provides
pinned source reconstructions, explicit semantic fixes and optional registry profiles.
The original and corrected executables are separate artifacts; qualification errors
exit nonzero. The corrected fixture pass is finite empirical evidence, not a proof
that every future returned weight-1 path is globally optimal. Native CSV cost and
search limits are retained alongside independently recomputed trajectory metrics.

The rectangle-depth correction additionally requires matching MDD and feasible-path
depths before MDD-based rectangle reasoning. Relaxed MDDs can still supply admissible
lower bounds; a shorter MDD cannot justify a strengthened split of a longer path.
Such cases use the ordinary conflict split. Native build/patch hashes identify this
change independently of the unchanged Python simulation version. Never pool the
old native binary's completed outcomes with the corrected native treatment.

Sources: [published article](https://link.springer.com/article/10.1007/s10458-024-09639-8), [EECBS driver](https://github.com/Jiaoyang-Li/EECBS/blob/main/src/driver.cpp), [CBSH2-RTC driver](https://github.com/Jiaoyang-Li/CBSH2-RTC/blob/main/src/driver.cpp), and the archived `NegotiationForMAPF` runner at revision `7e0e4ac09ee2604c23ba9c9851af6373cfc1ed7f` (`scripts/CBS Runs/run_cbs.py`).
