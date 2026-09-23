# Bounded event recording

`schema.py` defines the telemetry-2 discriminated union and nullable fields. `logger.py` uses a bounded queue, bounded backpressure, surfaced writer errors and immutable run directories. Complete compressed chunks are atomically published with checksums and an index. Recovery reads verified published chunks; queued or uncommitted events can be lost on a crash. The application trace collector separately bounds event counts and reports drops.

See [recording and replay contracts](../../../docs/gui/CONTRACTS.md).
