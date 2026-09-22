# Follow one recorded negotiation

Open the [offline narrated replay](assets/narrative/negotiation-story.html) to connect an offer, a response, its settlement, the recorded obligation and the next movement. No Python process, backend or internet connection is needed to play this file.

The example is an **actual execution of a synthetic teaching fixture**, produced by the four-trial [negotiation capsule](../examples/capsules/negotiation/README.md). It is not selected from the article cohort. [Narrative evidence](assets/narrative/negotiation-story.json) names the exact run, session, event sequence and frame for every step; [capture provenance](assets/narrative/provenance.json) identifies source and output hashes.

1. **Conflict context.** The session summary records the two participants and conflict location. It is logged after the offers; the explanation places it first to introduce the situation.
2. **Offers and responses.** Step through the actual offer messages and BID decisions. A path offer is a proposal, not an executed trajectory. Unknown utility values remain unavailable.
3. **Settlement.** Read the recorded amount. A zero settlement means no token changed hands; agreement does not imply a positive payment.
4. **Commitment.** Inspect the owner, reserved path and absolute start/end ticks in the following frame. Missing/expired records are not invented.
5. **Movement.** The next post-move frame and MOVE event show what occurred after the decision. A proposed path and an actual move have different evidence roles.

The offline replay has an agent table and the original evidence. For the GUI's richer views, use the same capsule workspace, select an agent in Inspect and enable reservations or recorded local view. These show different parts of the same evidence.

![Eighty HeatMap agents in a dense instance from the article settings](assets/gallery/article-16-80-overview.png)

*16×16 · 80 agents · HeatMap · Setting 4 · SC · FoV 5 · t=1. A separate, selected solved instance from the article settings. [Full gallery provenance](assets/gallery/provenance.json).*

![Selected agent with a recorded local view](assets/gallery/article-16-local-view.png)

*The same 16×16 instance, agent_049's recorded observation at t=1, displayed with the t=2 replay. It is not the narrated two-agent teaching run above.*

Next: [run the capsule yourself](../examples/capsules/negotiation/README.md) or inspect the [protocol contract](TAOP-CONFORMANCE.md).
