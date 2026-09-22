# Dense interactions, visible decisions

[Documentation index](README.md) · [GUI walkthrough](GUI-GUIDE.md) · [Alpha status](ALPHA-STATUS.md)

The complete replay and six GUI screenshots show two **solved modern executions from the article-verification population**: an empty 16×16 map with 80 agents, and a 32×32 map with approximately 20% obstacles and 80 agents. Both use HeatMap, Setting 4 and FoV 5. They illustrate local negotiation and constrained routing in DEC-MAPF, a Python research framework.

Select any image to open it at full resolution. Every image is an unmodified capture of the actual GUI serving a recorded run. Both trajectories passed independent validation. These are selected solved examples, not historical Java screenshots, estimates of success rate, a scaling study or a claim that all article results have been reproduced.

## Follow the complete negotiation

[![Complete recorded simulation following agent 2 through the 80-agent obstacle map](assets/gallery/negotiation-agent-2.gif)](assets/gallery/negotiation-agent-2-2048.gif)

**32×32 · 205 obstacles · 80 agents · HeatMap · Setting 4 · ZC · FoV 5.** The replay shows every integer tick from 0 to 50. Agent 2 moves 46 times, waits once, participates in five negotiations, and changes its remaining plan on five recorded steps. It reaches its goal at t=47; all agents finish by t=50. These counts describe this particular saved execution.

The white ring identifies agent 2; the cyan dashed square marks 5×5 FoV geometry. Executed paths, hindsight heat and recorded reservations are enabled. The view includes global replay context: neither the highlighted final route nor the pink heat should be interpreted as everything the agent knew at that tick. In Setting 4, agents disappear after their arrival tick; the GUI retains the selected FoV outline at its last recorded position.

Among all 80 agents, agent 2 combines the highest observed plan-change-tick count with the longest duration among tied agents. A change is counted after removing the first action from the preceding plan, so ordinary movement does not count as replanning. This measure does not count multiple intermediate revisions within a single tick.

The 51 frames play in a **30.6-second loop**, with 500 ms per ordinary tick and short opening, arrival and ending holds. Playback time is a presentation choice, not solver runtime. The grid was captured directly from the actual GUI; no intermediate positions or new trajectories were synthesized.

[2048-pixel animation](assets/gallery/negotiation-agent-2-2048.gif) · [Static alternative](assets/gallery/negotiation-agent-2-poster.png) · [Animation provenance and checksums](assets/gallery/animation-provenance.json).

## Dense empty-grid interactions

[![Actual GUI replay of 80 agents on a 16 by 16 empty grid](assets/gallery/article-16-80-overview.png)](assets/gallery/article-16-80-overview.png)

**16×16 · 80 agents · HeatMap · Setting 4 · SC · FoV 5 · t=1.** The initial roster occupies 80/256 = **31.25%** of the cells. Positions and goals remain readable with executed paths switched off. The selected run reaches all goals by t=25, with a sum of costs of 1,028 actions and 208 recorded negotiations. SC means **standard commitment**.

This is scenario `empty-16-16-random-80-agents-100`. The absence of obstacles does not remove interactions between agents; the local layers below show decisions made during this particular execution. The image does not establish that this is the hardest possible instance.

## Obstacles and local routing

[![Actual GUI replay of 80 agents on a 32 by 32 map with approximately 20 percent obstacles](assets/gallery/article-32-20-80-overview.png)](assets/gallery/article-32-20-80-overview.png)

**32×32 · 205 blocked cells · 80 agents · HeatMap · Setting 4 · ZC · FoV 5 · t=1.** The obstacle fraction is 205/1,024 = **20.0195%**. Initial agent occupancy is a different quantity: 80/819 = **9.7680% of free cells**. The selected run reaches all goals by t=50, with a sum of costs of 1,778 actions and 103 recorded negotiations.

This is scenario `random-32-32-20-random-80-agents-1`, from the article's 32×32 obstacle regime. ZC means zero commitment: it still protects the agreement tick before release. Neither the agent count nor these two examples establishes a ranking against other MAPF frameworks. The regimes have different geometry and commitment settings and must not be treated as a matched performance comparison.

## Actual local decision heat

[![Stored HeatMap strategy weights for agent_049 in the dense 16 by 16 run](assets/gallery/article-16-local-heat.png)](assets/gallery/article-16-local-heat.png)

**16×16 instance · agent_049 · decision t=1 · displayed frame t=2.** Teal cells show actual stored HeatMap weights for the selected decision, with 129 nonzero cells. The negotiating opponent is excluded from this recorded field. These are strategy inputs, not a heatmap reconstructed from the final trajectories. The GUI exposes numeric weights and their time slices; its labels distinguish the decision time from the following post-move frame.

## What one agent observed

[![The selected recipient's stored local observation, hiding unobserved global agents](assets/gallery/article-16-local-view.png)](assets/gallery/article-16-local-view.png)

**The same selected agent and observation tick.** This layer restricts moving-agent evidence to the recipient's recorded observation and received paths. The static map remains visible. Globally present agents that were absent from that observation are not inserted into the local view. The dashed square describes FoV geometry, while the stored observation establishes what was received.

## Commitments with time

[![Recorded finite reservations owned by agent_029 at tick three](assets/gallery/article-16-commitments.png)](assets/gallery/article-16-commitments.png)

**16×16 instance · agent_029 · t=3 · SC.** Amber cells and edges show this agent's recorded obligations over opponent allocations. Tick labels distinguish obligations at different times. The inspector and exported evidence retain their exact records. A visually highlighted reservation is not an unlimited promise over another agent's entire future trajectory.

## Follow one executed route

[![Selected executed trajectory through the 32 by 32 obstacle map](assets/gallery/article-32-selected-route.png)](assets/gallery/article-32-selected-route.png)

**32×32 instance · agent_000 · t=1.** Select one agent and enable executed paths to keep its trajectory prominent while the others fade. The highlighted full route includes hindsight relative to the displayed tick; it does not claim that the agent knew its final route at that moment. Use recorded plans, observations and session events to examine decision-time knowledge.

## Selection and recording

The source population is the preserved modern article-verification results. Within each requested regime, selection required `valid_solution`, HeatMap, Setting 4 and FoV 5, with SC for 16×16 and ZC for the 32×32/20% obstacle regime. We selected the first scenario name and trial ID in lexical order among qualifying solved records: 28 eligible 16×16 records and 25 eligible 32×32 records were present in the inspected preserved-results snapshot. This is explicitly conditional on solving, not a fastest-run or best-cost selection rule.

The original executions retained paths and metrics but used `metrics-only` recording. To obtain decision evidence, each selected case was executed once more with the **same frozen source, effective inputs, ordered roster and seed**, changing only the recording level to `full-trace`. Both diagnostic recordings passed independent validation and reproduced the exact per-agent paths, costs, makespan, negotiation counts and canonical sharing/detour metrics. Original artifacts were preserved and their checksums verified. These two recordings are not extra independent scientific replicates and are not appended to the article cohort.

[Image provenance](assets/gallery/provenance.json) links original and diagnostic run IDs, original controller/trial/artifact identities, source digest, configurations, layers, displayed ticks, renderer/capture hashes and image checksums. Views of heat and commitments select populated records in the first five ticks to explain the mechanisms. Wall-clock runtime shown in a screenshot belongs to the diagnostic recording under local load; it is not a speedup estimate or a substitute for the original benchmark timing.

Both executions use source digest `d5ee4cf9091946ea0eec8c91d613e24fcdf994e5772b2a2a161207aed488524a`. The checksum identifies the source that produced these saved trajectories; it is not a release label or a claim that the screenshots establish population performance. Use the [experiment workflow](EXPERIMENTS.md) to collect and compare outcomes across a declared study.

## Recreate the gallery

The capture script requires the completed full-trace workspace and a parity receipt linking it to the original outcomes. The repository includes screenshots and sanitized provenance, not the original experiment workspaces or raw datasets. A clean clone therefore does not contain these two replay artifacts. For an immediately runnable teaching workflow, use the [headless tutorial](HEADLESS.md) or [negotiation capsule](../examples/capsules/negotiation/README.md).

With the recorded workspace and its `PARITY-RECEIPT.json`, build the GUI as described in [Installation](INSTALLATION.md), then serve the stopped workspace in terminal 1:

```bash
MAPF_WORKSPACE_DIR=/path/to/completed/article-gallery/workspace uv run --no-sync mapf dashboard --host 127.0.0.1 --port 8000
```

In terminal 2:

```bash
node scripts/capture_article_examples.mjs --url http://127.0.0.1:8000 --selection /path/to/PARITY-RECEIPT.json --output runs/article-gallery/screenshots
uv run --no-sync python scripts/check_documentation.py
```

The script requires two parity-checked, independently valid, 80-agent runs with the expected source identities. It uses ordinary UI controls, refuses a non-local API and fails on browser page errors. It uses installed Chrome on macOS or Playwright Chromium elsewhere; `--channel chromium` overrides that choice. Review new images and receipts before replacing repository assets. Capture times, run/session IDs and runtime readouts need not match pixel-for-pixel on another execution.

The separate `documentation_examples.py` and `capture_documentation.mjs` helpers remain available for synthetic teaching and renderer exercises. Their output belongs under `runs/`; it is not the gallery of article settings above.
