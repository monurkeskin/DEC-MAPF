# Source and implementation traceability

Primary article: [JAAMAS 38:10](https://doi.org/10.1007/s10458-024-09639-8), sections 4–5. The inspected archived Java source is [NegotiationForMAPF at 7e0e4ac0](https://github.com/erancihan/NegotiationForMAPF/tree/7e0e4ac09ee2604c23ba9c9851af6373cfc1ed7f). This identifies the inspected code; it does not prove that revision generated the published experiment.

| Concept | Primary evidence | Current Python / verification |
|---|---|---|
| Acknowledgements and payment | Section 4, Fig.2; Java Action and NegotiationSession | `negotiation/ledger.py`, `taop_v2.py`; repeated-any-own-offer, funds, positive payment and atomic rollback witnesses |
| Fig.2 allocation | Published (3,2) at t1, (3,3) at t2; C receives two tokens | `test_taop_contracts.py`; exact published cells/payment and section4.1 role obligations; initial cells complete this local fixture |
| SC/DC/ZC | Section4.1, Fig.1b explanation | `core/commitments.py`, `agents/base.py`; acceptor-only finite allocation, absolute conflict boundary, multiple contracts |
| PathAware | Section4.2.1; archived PathAwareAgent | `agents/path_aware.py`; action-length ratios, cumulative acknowledgement, bounded search; scheduling/candidate differences remain explicit |
| HeatMap | Section4.2.2; archived HeatMapAgent | `agents/heatmap.py`; temporal/opponent exclusion and cache invalidation; finite kernel differs from Java CAP999 |
| Disclosure | Section5, Eq.3 | `metrics/communication.py`; actual recipient broadcasts, coordinate sets, bytes and separate space-time metric |
| Path difference | Section5, Eq.2 | `analytics/experiment.py`; common-solved selected-method reference; distinct individual lower-bound detour and qualified optimality gap |
| Physics | Four settings, discrete MAPF constraints | `solution_validator.py`, conflict/movement/search; independent tiny CBS oracle and adversarial paths |
| Experimental identity | Explicit scenario/configuration/source requirement | `application/experiments.py`, `article_suite.py`; frozen all-planned rows, source-file sampling clusters, explicit retry ancestry |
| Imported tables | Supplied aggregates and figures | `application/legacy.py`; quarantined until exact source inputs and metric definitions are established |

The printed payment expression conflicts with the article prose/example and Java settlement; the token protocol follows the documented positive difference. Java also charges the initial broadcast repetition, whereas the article prose starts the first new negotiation offer at zero. See [TAOP-CONFORMANCE.md](TAOP-CONFORMANCE.md) for the consequential distinctions. No inspected class name alone qualifies a scientific figure.
