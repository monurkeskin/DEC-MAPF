# Make one independently reviewable contribution

Start with a small change whose intended behavior and checks can be inspected together. The tasks below suggest useful places to contribute; discuss the specific problem and expected outcome in an issue before a substantial change.

| Contribution | Where to work | Acceptance before review |
| --- | --- | --- |
| Integrate a MAPF method | `solvers/`, reviewed request/capability composition, method tests | Follow [the extension guide](EXTENDING.md); declare information access, supported settings, method identity and termination; validate trajectories and real spawned-worker execution |
| Add a licensed teaching scenario | `examples/`, `docs/SCENARIOS.md`, scenario tests | Attribute its source/license; validate coordinates, roster and setting; keep raw research data out; demonstrate a bounded run and all outcomes |
| Explain a confusing replay layer | `docs/GLOSSARY.md`, `docs/GALLERY.md`, capture script | Preserve the real run/tick; identify local evidence versus hindsight; add alt text; pass docs/link checks |
| Add an adversarial importer fixture | `tests/test_workspace_invariants.py`, `application/artifacts.py` | Start with a failing meaningful malformed input; reject it without changing the source bundle or creating misleading evidence |
| Improve a keyboard interaction | `frontend/src/components/`, `frontend/tests/` | Show the failing interaction, preserve focus and labels, pass browser/axe checks; do not claim universal screen-reader acceptance |
| Clarify a headless task guide | `docs/HEADLESS.md`, `examples/capsules/` | Execute the documented command against an installed wheel outside the checkout; retain the output contract and any limitations |

Pick an existing problem or an actual reader report. Do not create work merely to satisfy a checklist. Explain which domain/service/adapter owns a change; keep a feature out of the solver core when it belongs to presentation or persistence. Propose method changes separately because they alter the scientific comparison contract.

Next: read [CONTRIBUTING](../CONTRIBUTING.md), [the project map](PROJECT-MAP.md) and [public API boundaries](PUBLIC-API.md).
