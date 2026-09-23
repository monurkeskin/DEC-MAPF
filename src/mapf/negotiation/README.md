# Protocol and commitment settlement

`taop_v2.py` implements the current `taop-v2` token/concession protocol selected by application and simulation defaults. `taop.py` retains the explicitly selected `taop-v1` acknowledgement variant. `ledger.py` atomically settles both owned states with token conservation. `session.py` dispatches these protocols and retains the explicit legacy alternating mode; its low-level constructor has a compatibility default, so new callers should specify the protocol. The protocol guide explains the printed article payment-sign ambiguity and the Java initial-broadcast difference.

See [protocol rules and source interpretation](../../../docs/TAOP-CONFORMANCE.md).
