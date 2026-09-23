# Decentralized strategy implementations

`base.py` owns mutable agent state, path application and commitments. `path_aware.py` and `heatmap.py` implement the named modern variants; `greedy.py` includes Greedy and Conceder. Strategies receive immutable local observations and static geometry, not the global agent registry. HeatMap weights are time-indexed and exclude the negotiating opponent. SC/DC/ZC obligations apply to the acceptor and finite allocated opponent subpaths.

See [protocol and commitment rules](../../../docs/TAOP-CONFORMANCE.md).
