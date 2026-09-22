# Bounded event recording

`schema.py` defines the telemetry-2 discriminated union and nullable fields. `logger.py` uses a bounded queue, bounded backpressure, surfaced writer errors and immutable run directories. Complete compressed chunks are atomically published with checksums and an index. Recovery reads verified published chunks; queued or uncommitted events can be lost on a crash. No zero-overhead, universal durability or constant-time seek claim is made. The application trace collector separately bounds event counts and reports drops.

See the [current contract](../../../docs/gui/CONTRACTS.md), the source interfaces and executable tests.
