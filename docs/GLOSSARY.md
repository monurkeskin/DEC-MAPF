# Read the simulation and its visuals consistently

Use these terms when describing a replay, experiment or comparison. The same meanings apply with and without the GUI.

| Term or mark | Meaning |
| --- | --- |
| DEC-MAPF | This modern Python repository/distribution; `mapf` is its CLI/import |
| Scenario / instance | Grid, obstacles, ordered roster, starts/goals and problem setting; identity is recorded |
| Trial / attempt / run | A planned treatment / one explicit execution attempt / its committed result; retries are not independent scenarios |
| Tick `t=0` | Initial physical state; post-move frame `t+1` follows decisions at `t` |
| FoV | Square communication neighborhood, not complete global agent knowledge |
| Offer / acknowledgement / payment | Proposed allocation / accumulated protocol usage / actual settlement; zero settlement is possible |
| Commitment SC / DC / ZC | Standard / dynamic / zero-horizon policy; the agreed immediate move still has obligations |
| `completed` | The worker committed a result; may still be an unsolved valid prefix |
| `valid_solution` / `valid_prefix` | Complete independently checked solution / physically checked incomplete trajectory |
| Timeout | A recorded deadline outcome; distinguish bilateral negotiation, whole-process and administrative batch budgets |
| Circle / outlined square / dark cell | Agent / goal / obstacle |
| Bright selected route / dim routes | Selected agent trajectory / other trajectories; executed full routes include hindsight |
| Dashed FoV / recipient-local view | Geometric neighborhood / recorded received information |
| Amber reservation | Recorded time-indexed obligation; read owner and absolute tick labels |
| Teal local heat | Stored strategy weights for the named agent/session/tick; distinct from hindsight occupancy |
| Saved replay / live job | Committed evidence / ongoing computation; replay playback does not rerun a solver |

A visual caption states **grid · roster · method · setting · relevant FoV/commitment · tick**, then what the layer represents and the evidence limit. A teaching figure identifies its synthetic input and actual execution. Runtime, source hash, run ID and capture provenance are retained with it. Do not use a screenshot to establish scalability, statistical superiority or inaccessible agent knowledge.

For new desktop captures, start at 1440×1000 or larger for dense grids; preserve aspect ratio, provide descriptive alt text and make full resolution available. Use both a large overview and a selected-agent view. Test light/dark contrast and keyboard access. Personal color and density preference still needs the reader's judgment.

Next: use the [gallery](GALLERY.md) to identify the layers, or follow [one recorded negotiation](NEGOTIATION-WALKTHROUGH.md).
