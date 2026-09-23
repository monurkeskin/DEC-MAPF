# Discrete joint simulation

The ordered pipeline captures recipient observations, detects communicated conflicts, negotiates, resolves joint moves and records post-move snapshots. Initial state is t=0. Local fallback views are captured before any agent moves. Every joint move must respect waiting permission, live commitments and future parked-goal occupancy. Bounded joint repair may recover a blocked proposal; otherwise the whole step stops before movement or clock advancement. The independent validator controls physical success. A bounded failed replan or joint repair does not prove that the original instance is unsolvable.

See [pipeline and movement semantics](../../../docs/ALGORITHM.md).
