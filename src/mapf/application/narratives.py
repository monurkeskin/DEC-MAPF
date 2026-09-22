"""Narrate recorded evidence without inferring unavailable decisions or transfers."""
from __future__ import annotations

import html
import json
from typing import Any

from mapf.application.artifacts import standalone_html


def negotiation_story(payload: dict[str, Any]) -> dict[str, Any]:
    """Select the first agreed session; reference actual event sequences and frames.

    This is an explanatory projection, not independent trajectory qualification.
    Reduced/legacy recordings may have no narratable session and are rejected.
    """
    events = payload["result"].get("telemetry_events", [])
    session = next((e for e in events if e.get("event_type") == "NEGO_SESSION" and e.get("outcome") == "AGREED"), None)
    if session is None:
        raise ValueError("No recorded agreed negotiation; full-trace evidence required")
    sid, tick = session["session_id"], session["tick"]
    participants = [session["initiator_id"], session["opponent_id"]]
    selected = [e for e in events if e.get("session_id") == sid]
    steps: list[dict[str, Any]] = []

    def add(kind: str, text: str, event: dict[str, Any]) -> None:
        steps.append({"kind": kind, "text": text, "tick": event["tick"], "event_sequence": event["sequence"],
                      "reference": f"result.telemetry_events[sequence={event['sequence']}]", "evidence": event})

    add("conflict", f"{participants[0]} and {participants[1]} negotiated at t={tick}. The session summary records conflict cell ({session.get('conflict_x')}, {session.get('conflict_y')}). This summary is logged after the offers.", session)
    for event in selected:
        if event["event_type"] == "MESSAGE" and event.get("kind") == "OFFER":
            add("offer", f"{event['sender']} sent {event['recipient']} a path offer with acknowledgement {event.get('acknowledgement', 'unavailable')}.", event)
        elif event["event_type"] == "BID":
            add("response", f"Recorded response: {event.get('decision', 'unavailable')}. Inspect the raw response_evaluation for the recorded reason; missing utilities are unavailable.", event)
    transfer = next((e for e in selected if e["event_type"] == "TOKEN_TRANSFER"), None)
    if transfer is not None:
        amount = transfer["amount"]
        message = ("The recorded settlement is zero: no token changed hands in this session." if amount == 0 else
                   f"The recorded settlement transfers {amount} tokens from {transfer['payer']} to {transfer['payee']}.")
        add("settlement", message, transfer)
    else:
        amount = None
        add("settlement", "Token settlement evidence is unavailable; no amount is inferred.", session)
    next_tick = tick + 1
    frame = next((f for f in payload["frames"] if f["tick"] == next_tick), None)
    obligations = [c for cs in (frame or {}).get("commitments", {}).values() for c in cs if c.get("contract_id") == sid]
    steps.append({"kind": "commitment", "tick": next_tick if frame else tick, "event_sequence": None,
                  "reference": f"frames[{next_tick}].commitments" if frame else "unavailable",
                  "text": ("The next post-move frame retains the listed obligations. Their owner, absolute start/end ticks and reserved path define the scope." if obligations else
                           "A retained commitment in the next frame is unavailable. It may have expired or not been recorded; this view does not infer a violation."), "evidence": obligations})
    for event in events:
        if event.get("event_type") == "MOVE" and event.get("tick") == next_tick and event.get("agent_id") in participants:
            add("move", f"At t={next_tick}, {event['agent_id']} is at ({event['x']}, {event['y']}). This is executed movement, distinct from the earlier offered path.", event)
    return {"schema_version": "negotiation-story-1", "run_id": payload["metadata"]["run_id"],
            "session_id": sid, "participants": participants, "amount": amount, "steps": steps,
            "scope": "Actual recorded execution of a supplied scenario; narration is not a population estimate or proof of protocol correctness."}


def narrated_html(payload: dict[str, Any]) -> str:
    """Offline replay with accessible evidence steps; no network or solver needed."""
    story = negotiation_story(payload)
    raw = json.dumps(story).replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
    overview = "<section aria-label='Recorded negotiation walkthrough'><h2>Follow one recorded negotiation</h2><p>" + html.escape(story["scope"]) + "</p><div id='story-steps'></div><p id='story-text' role='status'></p><details><summary>Exact evidence for this step</summary><pre id='story-evidence'></pre></details></section>"
    page = standalone_html(payload).replace('<canvas id="grid">', overview + '<canvas id="grid">')
    page = page.replace('</style>', """body{padding:0 20px;color:#17384a;background:#f6f8fa}h1,h2{color:#15384b}
button{border:1px solid #91a4b1;border-radius:6px;background:#fff;color:#17384a;padding:8px 12px;cursor:pointer}
button:focus-visible{outline:3px solid #0f766e}button[aria-pressed=true]{background:#17384a;color:white}
#story-steps{display:flex;flex-wrap:wrap;gap:6px}#story-steps button{margin:0}#story-text{padding:14px;background:#e1efea;border-left:4px solid #0f766e}
#grid{display:block;width:min(100%,420px);height:auto;margin:20px 0;image-rendering:pixelated;background:white}
#story-evidence{max-height:240px;overflow:auto;background:white;padding:12px;font-size:13px;overflow-wrap:anywhere}
</style>""")
    script = '''<script type="application/json" id="story-data">''' + raw + '''</script><script>
const story=JSON.parse(document.getElementById('story-data').textContent);
const steps=document.getElementById('story-steps');
story.steps.forEach((step,i)=>{const b=document.createElement('button');b.textContent=(i+1)+'. '+step.kind+' · t='+step.tick;
b.setAttribute('aria-pressed','false');b.onclick=()=>{for(const button of steps.children)button.setAttribute('aria-pressed',String(button===b));slider.value=Math.min(frames.length-1,step.tick);draw();document.getElementById('story-text').textContent=step.text;
document.getElementById('story-evidence').textContent=JSON.stringify({run:story.run_id,session:story.session_id,reference:step.reference,evidence:step.evidence},null,2);};steps.append(b);});
steps.firstChild?.click();</script>'''
    return page.replace('</html>', script + '</html>')
