"""Portable checked bundles and offline exports derived from committed evidence."""

from __future__ import annotations

import csv
import html
import io
import json
from typing import Any

from mapf.application.contracts import SolverRunResult
from mapf.application.plans import instance_from_snapshot
from mapf.application.runs import RunRepository, digest, new_id
from mapf.application.scenarios import ScenarioService
from mapf.core.models import Path, Point, SimulationSetting
from mapf.core.solution_validator import validate_solution

METRICS: dict[str, dict[str, str]] = {
    "makespan": {
        "unit": "ticks",
        "formula": "max_i first_goal_arrival_tick_i",
        "population": "independently valid solved pairs",
    },
    "sum_of_costs": {
        "unit": "actions",
        "formula": "sum_i first_goal_arrival_tick_i",
        "population": "independently valid solved pairs",
    },
    "runtime_ms": {
        "unit": "ms",
        "formula": "monotonic duration of solver.solve; validation, queue and process startup excluded",
        "population": "completed runs; timeouts are censored",
    },
    "information_sharing_rate": {
        "unit": "fraction",
        "formula": "mean over ordered distinct sender-recipient pairs of broadcast-disclosed executed coordinate coverage",
        "population": "delivered-metrics-v2 decentralized runs; unavailable for centralized or unqualified historical runs",
    },
}


def export_bundle(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "format": "decmapf-run",
        "version": "1.0",
        "canonicalization": "RFC8785",
        "sha256": digest(payload),
        "payload": payload,
    }


def import_bundle(bundle: dict[str, Any], repository: RunRepository) -> str:
    if bundle.get("format") != "decmapf-run" or bundle.get("version") != "1.0":
        raise ValueError(
            "Unsupported bundle format/version; legacy archives require the quarantine importer"
        )
    payload = bundle.get("payload")
    if not isinstance(payload, dict) or digest(payload) != bundle.get("sha256"):
        raise ValueError("Bundle checksum mismatch")
    payload = json.loads(json.dumps(payload))
    meta = payload["metadata"]
    result = SolverRunResult.model_validate(payload["result"])
    inst = instance_from_snapshot(meta["instance"])
    setting = SimulationSetting[meta["setting"]]
    errors = ScenarioService.validate_instance(inst, setting)
    if errors:
        raise ValueError("Invalid bundle scenario: " + "; ".join(errors))
    actual = validate_solution(
        inst,
        {
            a: Path(points=[Point(p.x, p.y) for p in pts])
            for a, pts in result.paths.items()
        },
        setting,
    )
    if result.validation is None or actual.is_valid != result.validation.is_valid:
        raise ValueError(
            "Bundle independent-validation receipt does not match its paths"
        )
    from dataclasses import asdict

    if digest([asdict(e) for e in actual.errors]) != digest(result.validation.errors):
        raise ValueError(
            "Bundle validation errors do not match independently recomputed errors"
        )
    if result.success and not actual.is_valid:
        raise ValueError("Invalid paths cannot be a successful run")
    if payload.get("frames") != payload["result"]["frames"]:
        raise ValueError("Bundle frame representations disagree")
    for t, frame in enumerate(result.frames):
        if frame.tick != t or frame.targets != {
            a: [p.x, p.y] for a, p in inst.goals.items()
        }:
            raise ValueError(
                "Bundle replay timeline or goals disagree with its scenario"
            )
        for aid, path in result.paths.items():
            if path and frame.positions.get(aid) != [
                path[min(t, len(path) - 1)].x,
                path[min(t, len(path) - 1)].y,
            ]:
                raise ValueError("Bundle replay positions disagree with its paths")
    from mapf.core.hashing import compute_instance_hash

    if len(result.frames) > 501 or len(result.paths) > 100:
        raise ValueError("Bundle exceeds supported replay limits")
    recorded_makespan = max((len(p) - 1 for p in result.paths.values()), default=0)
    if meta.get("frame_count") != len(result.frames):
        raise ValueError("Bundle declared frame count disagrees with recorded replay")
    reduced = meta["effective_config"].get("recording_level") == "metrics-only"
    if reduced and result.frames:
        raise ValueError("Metrics-only bundle unexpectedly contains replay frames")
    if not reduced and len(result.frames) != recorded_makespan + 1:
        raise ValueError("Bundle replay length does not match its recorded paths")
    from mapf.metrics.costs import trajectory_costs
    costs = trajectory_costs(inst, {a: Path(points=[Point(p.x, p.y) for p in pts])
                                    for a, pts in result.paths.items()})
    expected_soc = costs["action_sum_of_costs"] if result.success else costs["recorded_action_count"]
    expected_makespan = costs["action_makespan"] if result.success else recorded_makespan
    if result.makespan != expected_makespan or result.sum_of_costs != expected_soc:
        raise ValueError("Bundle canonical costs do not match its paths")
    if (
        meta["instance_hash"] != compute_instance_hash(inst, setting)
        or result.instance_hash != meta["instance_hash"]
    ):
        raise ValueError("Bundle scenario identity mismatch")
    for key in ("success", "makespan", "sum_of_costs", "runtime_ms"):
        if meta[key] != getattr(result, key):
            raise ValueError(f"Bundle metadata disagrees with result: {key}")
    if (
        meta["is_valid"] != actual.is_valid
        or meta["validation_status"] != result.validation.status
    ):
        raise ValueError("Bundle metadata misrepresents validation")
    if (
        meta["effective_config"]["setting"] != meta["setting"]
        or meta["instance"]["setting"] != meta["setting"]
    ):
        raise ValueError("Bundle effective setting mismatch")
    definition = {
        "instance_hash": meta["instance_hash"],
        "effective_config": meta["effective_config"],
        "algorithm_version": meta["provenance"]["algorithm_version"],
    }
    if meta["definition_digest"] != digest(definition):
        raise ValueError("Bundle effective-input digest mismatch")
    run_id = new_id("run")
    meta["imported_from_run_id"] = meta["run_id"]
    meta["run_id"] = run_id
    meta["import_validation"] = (
        "trajectory-v2; checksum is integrity, not source authentication"
    )
    payload["result"]["run_id"] = run_id
    repository.save_run(payload)
    return run_id


def metrics_csv(payload: dict[str, Any]) -> str:
    out = io.StringIO()
    keys = [
        "run_id",
        "instance_hash",
        "solver_name",
        "setting",
        "success",
        "validation_status",
        "makespan",
        "sum_of_costs",
        "runtime_ms",
    ]
    writer = csv.DictWriter(out, fieldnames=keys, lineterminator="\n")
    writer.writeheader()
    # Spreadsheet formula injection: preserve the raw value in JSON; escape the presentation CSV.
    row = {k: payload["metadata"][k] for k in keys}
    for key, val in row.items():
        if isinstance(val, str) and val.startswith(("=", "+", "-", "@")):
            row[key] = "'" + val
    writer.writerow(row)
    return out.getvalue()


def latex_table(payload: dict[str, Any]) -> str:
    def esc(text: Any) -> str:
        return "".join(
            {
                "\\": r"\textbackslash{}",
                "_": r"\_",
                "%": r"\%",
                "&": r"\&",
                "#": r"\#",
                "{": r"\{",
                "}": r"\}",
                "$": r"\$",
                "~": r"\textasciitilde{}",
                "^": r"\textasciicircum{}",
            }.get(c, c)
            for c in str(text)
        )

    m = payload["metadata"]
    return "\n".join(
        [
            r"\begin{tabular}{lrrl}",
            r"Solver & SOC & Makespan & Validation \\",
            " & ".join(
                esc(m[k])
                for k in (
                    "solver_name",
                    "sum_of_costs",
                    "makespan",
                    "validation_status",
                )
            )
            + r" \\",
            r"\end{tabular}",
            f"% Run {m['run_id']}; metric definitions: workspace-metrics-v1",
        ]
    )


def svg_snapshot(payload: dict[str, Any], tick: int = 0) -> str:
    snap = payload["metadata"]["instance"]
    frames = payload["frames"]
    if not 0 <= tick < len(frames):
        raise ValueError("Tick is outside this replay")
    frame = frames[tick]
    w, h, cell = snap["grid_width"], snap["grid_height"], 32
    elements = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w * cell} {h * cell + 30}" role="img">',
        f"<title>DEC-MAPF {html.escape(payload['metadata']['run_id'])} at tick {tick}</title>",
        '<rect width="100%" height="100%" fill="#ffffff"/>',
    ]
    for x in range(w + 1):
        elements.append(f'<path d="M{x * cell} 0V{h * cell}" stroke="#cbd5e1"/>')
    for y in range(h + 1):
        elements.append(f'<path d="M0 {y * cell}H{w * cell}" stroke="#cbd5e1"/>')
    for x, y in snap["obstacles"]:
        elements.append(
            f'<rect x="{x * cell}" y="{y * cell}" width="32" height="32" fill="#334155"/>'
        )
    for aid, (x, y) in snap["goals"].items():
        elements.append(
            f'<rect x="{x * cell + 5}" y="{y * cell + 5}" width="22" height="22" fill="none" stroke="#0f766e"><title>{html.escape(aid)} goal</title></rect>'
        )
    for aid, (x, y) in frame["positions"].items():
        if frame["statuses"].get(aid) == "disappeared":
            continue
        elements.append(
            f'<circle cx="{x * cell + 16}" cy="{y * cell + 16}" r="10" fill="#0369a1"><title>{html.escape(aid)}</title></circle>'
        )
    elements.append(
        f'<text x="4" y="{h * cell + 21}" font-size="12">t={tick}; {html.escape(payload["metadata"]["validation_status"])}</text></svg>'
    )
    return "".join(elements)


def standalone_html(payload: dict[str, Any]) -> str:
    # Use JSON as inert script data; escape script terminators and HTML-significant characters.
    raw = (
        json.dumps(payload)
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("&", "\\u0026")
    )
    return (
        """<!doctype html><html lang="en"><meta charset="utf-8"><title>DEC-MAPF offline replay</title>
<style>body{font:16px system-ui;max-width:1000px;margin:30px auto}canvas{max-width:100%;border:1px solid #cbd5e1}pre{white-space:pre-wrap}button,input,select{margin:8px}label{display:inline-block}#heat-status{min-height:1.4em}</style>
<h1>DEC-MAPF offline replay</h1><p id="receipt"></p><button id="prev">Previous</button><button id="next">Next</button><label>Tick <input id="tick" type="range" min="0" value="0"></label><output id="time"></output><br><label>Recorded local heat <select id="heat"><option value="">None</option></select></label><label>Heat time slice <select id="heat-slice"><option value="-1">Aggregate</option></select></label><p id="heat-status" role="status"></p><canvas id="grid"></canvas><details><summary>Agent table and provenance</summary><pre id="details"></pre></details>
<script type="application/json" id="data">"""
        + raw
        + """</script><script>
const p=JSON.parse(document.getElementById('data').textContent),s=p.metadata.instance,frames=p.frames;
const slider=document.getElementById('tick'),c=document.getElementById('grid'),ctx=c.getContext('2d');
slider.max=Math.max(0,frames.length-1);
if(!frames.length){slider.disabled=true;document.getElementById('prev').disabled=true;document.getElementById('next').disabled=true;}
c.width=s.grid_width*24;c.height=s.grid_height*24;
document.getElementById('receipt').textContent=p.metadata.run_id+'; validation: '+p.metadata.validation_status;
const heat=document.getElementById('heat'),slice=document.getElementById('heat-slice');
function option(select,value,label){const o=document.createElement('option');o.value=value;o.textContent=label;select.append(o);}
function draw(){
  const t=Number(slider.value),f=frames[t],records=f?.local_heat||[],previous=heat.value;
  heat.replaceChildren();option(heat,'','None');
  for(const r of records)option(heat,r.record_id,r.agent_id+'; decision t='+r.tick+'; opponent '+(r.opponent_id??'none')+'; '+r.session_id);
  heat.value=records.some(r=>r.record_id===previous)?previous:'';
  const record=records.find(r=>r.record_id===heat.value),offset=slice.value;
  slice.replaceChildren();option(slice,'-1','Aggregate planning weights');
  if(record?.status==='recorded')record.fields.forEach((_,i)=>option(slice,String(i),'Relative t+'+i+'; absolute t='+(record.tick+i)));
  slice.value=record&&Number(offset)<record.fields.length?offset:'-1';
  let field={};
  const status=document.getElementById('heat-status');
  if(!record)status.textContent=records.length?'Select a recorded decision.':'No recorded decision heat in this frame. Older and reduced recordings may not contain it.';
  else if(record.status!=='recorded')status.textContent='Local heat recording budget exhausted; values unavailable.';
  else {field=Number(slice.value)<0?record.aggregate:record.fields[Number(slice.value)];status.textContent='Actual strategy weights: decision t='+record.tick+', agent '+record.agent_id+', opponent '+(record.opponent_id??'none')+' excluded. Captured before movement; displayed with the following post-move frame.';}
  if(f?.local_heat_omitted)status.textContent+=' '+f.local_heat_omitted+' heat records omitted by budget at this step.';
  ctx.fillStyle='#f8fafc';ctx.fillRect(0,0,c.width,c.height);
  const maximum=Math.max(1,...Object.values(field));
  for(const [cell,value] of Object.entries(field)){const [x,y]=cell.split('-').map(Number);ctx.fillStyle='rgba(13,148,136,'+(0.15+0.65*value/maximum)+')';ctx.fillRect(x*24,y*24,24,24);}
  ctx.strokeStyle='#cbd5e1';for(let y=0;y<s.grid_height;y++)for(let x=0;x<s.grid_width;x++)ctx.strokeRect(x*24,y*24,24,24);
  ctx.fillStyle='#334155';for(const [x,y] of s.obstacles)ctx.fillRect(x*24,y*24,24,24);
  ctx.strokeStyle='#0f766e';for(const [x,y] of Object.values(s.goals))ctx.strokeRect(x*24+4,y*24+4,16,16);
  if(f){for(const [a,[x,y]] of Object.entries(f.positions)){if(f.statuses[a]==='disappeared')continue;ctx.fillStyle='#0369a1';ctx.beginPath();ctx.arc(x*24+12,y*24+12,8,0,Math.PI*2);ctx.fill();}document.getElementById('details').textContent=JSON.stringify({selected_heat:record||null,selected_field:field,frame:f,metadata:p.metadata},null,2);}
  if(!f)document.getElementById('details').textContent=JSON.stringify({metadata:p.metadata,paths:p.result.paths,availability:'No recorded replay frames'},null,2);
  document.getElementById('time').textContent=frames.length?'t='+t:'No recorded replay frames; executed paths retained.';
}
heat.onchange=()=>{slice.value='-1';draw()};slice.onchange=draw;
slider.oninput=draw;document.getElementById('prev').onclick=()=>{slider.value=Math.max(0,Number(slider.value)-1);draw()};document.getElementById('next').onclick=()=>{slider.value=Math.min(frames.length-1,Number(slider.value)+1);draw()};draw();</script></html>"""
    )
