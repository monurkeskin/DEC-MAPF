# Optional local HTTP adapter

`app.py` composes the FastAPI application. `_services.py:WorkspaceServices` owns
lazy initialization and shutdown of the shared repository, supervisor and
experiment coordinator. `_api_*.py` modules adapt one resource family each;
application services own validation, scheduling, persistence and scientific
interpretation. `_event_stream.py` owns transport cursors and heartbeats.

The React client uses `/api/v1`. `_legacy_*.py` modules preserve explicit
compatibility routes and response shapes; new workflows use the versioned
application API. Start with the [frontend guide](../../../frontend/README.md),
[workspace contracts](../../../docs/gui/CONTRACTS.md) and
[code reading guide](../../../docs/CODE-GUIDE.md).
