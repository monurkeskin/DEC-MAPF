# Negotiation capsule

**Question:** How does a recorded agreement constrain the next movement?

This is a complete teaching workflow over two built-in scenarios. The explicit
[study.json](study.json) freezes the methods, settings, seeds and sampling claim.
It is not an article benchmark or evidence of a method advantage.

```bash
python examples/capsules/negotiation/run.py --output runs/negotiation-capsule
```

A core-only installed wheel suffices. Run from the repository root, or copy this
whole directory elsewhere and run `python run.py --output /path/to/new/output`.
The output directory must not exist. The study uses one worker, at most 120 batch
seconds and 256 MiB of workspace artifacts; per-process limits are in study.json.
Exports add a small amount of storage beyond the workspace quota.

Inspect `receipt.json`, `experiment-card.json`, and **all** `all-trials.json` rows.
Each completed run has a checked `bundle.json`, offline `replay.html` and
`initial.svg`. An agreed negotiation also produces `negotiation-story.html` and
its exact event/frame references. The receipt records observed wall time and
output bytes with the platform; peak RAM is explicitly unmeasured.

Expected qualification: all declared teaching trials should yield independent
`valid_solution` receipts. The program preserves other outcomes and exits 2 if
this expectation is not met; it never silently retries. A completed job alone
does not imply a solution. Runtime/IDs and process timing may vary across machines.

Next: use [the headless guide](../../../docs/HEADLESS.md) to declare your own
population and budgets; retain unsuccessful outcomes in the denominator.
