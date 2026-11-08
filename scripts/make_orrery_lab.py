"""Build the ORRERY celestial lab: a self-contained, offline, CSP-locked HTML page.

Usage::

    uv run python scripts/make_orrery_lab.py [--gmat] [--out docs/orrery-lab.html]

Every number in the page is computed here by the ORRERY engine (no values are
drawn by hand and no network is used at view time). The page embeds the data as
a JSON island and renders it with one inline script and one inline stylesheet,
each pinned by its SHA-256 in a strict Content-Security-Policy, matching the
offline observatory's security model. With ``--gmat`` the drift panel uses the
committed GMAT reference trajectories; otherwise that panel is omitted.

Views: orbit gallery (ECI projections), predicted-vs-reference drift, a civilian
Hohmann transfer, integrator-tolerance effect, propagator comparison, and a
covariance uncertainty envelope.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import math
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
import sys  # noqa: E402

sys.path.insert(0, str(ROOT / "src"))

from rain_atlas.orrery import gmat, scenarios  # noqa: E402
from rain_atlas.orrery.constants import GMAT_CONSTANTS as C  # noqa: E402
from rain_atlas.orrery.covariance import covariance_study  # noqa: E402
from rain_atlas.orrery.kepler import elements_to_state, kepler_trajectory, orbital_period  # noqa: E402
from rain_atlas.orrery.propagate import position_velocity_errors, propagate  # noqa: E402
from rain_atlas.orrery.transfers import hohmann_maneuvers  # noqa: E402

MU = C["earth_mu_km3_s2"]
RE = C["earth_radius_km"]


def _sample(states: np.ndarray, n: int = 400) -> list[list[float]]:
    idx = np.linspace(0, len(states) - 1, min(n, len(states))).round().astype(int)
    return [[round(float(states[i, k]), 3) for k in range(3)] for i in idx]


def orbit_gallery() -> list[dict]:
    out = []
    for name, color in (
        ("S1-leo-twobody", "#4cc9f0"),
        ("S2-molniya-twobody", "#f72585"),
        ("S3-geo-twobody", "#ffd166"),
        ("S8-earth-moon-tli", "#a0e8af"),
    ):
        scen = scenarios.scenario(name)
        cfg = dict(scen["config"])
        cfg["output_step_s"] = cfg["duration_s"] / 1500.0
        traj = propagate(cfg)
        out.append(
            {
                "name": name,
                "title": scen["title"],
                "color": color,
                "duration_days": round(cfg["duration_s"] / 86400.0, 2),
                "points": _sample(traj.states, 500),
            }
        )
    return out


def drift_panel(use_gmat: bool) -> list[dict]:
    if not use_gmat:
        return []
    out = []
    for name in scenarios.GMAT_SCENARIOS:
        if not (gmat.REFERENCE_DIR / f"{name}.json").exists():
            continue
        record = gmat.load_reference(name)
        ref = gmat.reference_arrays(record)
        cfg = dict(scenarios.scenario(name)["config"])
        cfg["output_times_s"] = ref["elapsed_s"].tolist()
        cfg["integrator"] = {"method": "rkf78", "rtol": 1e-12, "atol": 1e-12}
        traj = propagate(cfg)
        err = position_velocity_errors(traj.states, ref["mj2000"])
        step = max(1, len(ref["elapsed_s"]) // 300)
        out.append(
            {
                "name": name,
                "title": scenarios.scenario(name)["title"],
                "hours": [round(t / 3600.0, 4) for t in ref["elapsed_s"][::step]],
                "error_m": [round(e, 6) for e in err["position_error_m"][::step]],
                "max_error_m": round(err["max_position_error_m"], 4),
            }
        )
    return out


def transfer_panel() -> dict:
    r1 = RE + 400.0
    r2 = 42164.0
    r0, v0 = elements_to_state(r1, 0.0, 0.0, 0.0, 0.0, 0.0, MU)
    plan = hohmann_maneuvers(r0, v0, r2, MU)
    park = propagate(
        {
            "initial_state": list(r0) + list(v0),
            "duration_s": orbital_period(r1, MU),
            "output_step_s": orbital_period(r1, MU) / 300,
            "forces": {"earth": {"model": "point-mass"}},
        }
    )
    burn1 = np.asarray(plan["maneuvers"][0]["dv_km_s"])
    xfer = propagate(
        {
            "initial_state": list(r0) + list(v0 + burn1),
            "duration_s": plan["time_of_flight_s"],
            "output_step_s": plan["time_of_flight_s"] / 400,
            "forces": {"earth": {"model": "point-mass"}},
        }
    )
    final = xfer.states[-1]
    geo = propagate(
        {
            "initial_state": final.tolist(),
            "duration_s": orbital_period(r2, MU),
            "output_step_s": orbital_period(r2, MU) / 300,
            "forces": {"earth": {"model": "point-mass"}},
        }
    )
    return {
        "park": _sample(park.states, 300),
        "transfer": _sample(xfer.states, 400),
        "geo": _sample(geo.states, 300),
        "dv1_km_s": round(plan["dv1_km_s"], 5),
        "dv2_km_s": round(plan["dv2_km_s"], 5),
        "total_dv_km_s": round(plan["total_dv_km_s"], 5),
        "tof_hours": round(plan["time_of_flight_s"] / 3600.0, 3),
        "r1_km": round(r1, 1),
        "r2_km": round(r2, 1),
    }


def tolerance_panel() -> dict:
    scen = scenarios.scenario("S4-leo-j2")
    base = dict(scen["config"])
    base["output_step_s"] = 120.0
    ref = propagate({**base, "integrator": {"method": "rkf78", "rtol": 1e-13, "atol": 1e-13}})
    series = []
    for tol in (1e-6, 1e-8, 1e-10, 1e-12):
        traj = propagate({**base, "integrator": {"method": "rkf78", "rtol": tol, "atol": tol}})
        err = position_velocity_errors(traj.states, ref.states)
        step = max(1, len(traj.times) // 250)
        series.append(
            {
                "tol": tol,
                "hours": [round(t / 3600, 4) for t in traj.times[::step]],
                "error_m": [round(e, 6) for e in err["position_error_m"][::step]],
                "steps": traj.stats["accepted_steps"],
            }
        )
    return {"title": scen["title"], "series": series}


def propagator_panel() -> dict:
    r0, v0 = elements_to_state(7000.0, 0.01, math.radians(30), 0.3, 0.5, 0.2, MU)
    period = orbital_period(7000.0, MU)
    times = np.linspace(0, 5 * period, 300)
    truth = kepler_trajectory(r0, v0, times, MU)
    cfg0 = {
        "initial_state": list(r0) + list(v0),
        "output_times_s": times.tolist(),
        "forces": {"earth": {"model": "point-mass"}},
    }
    series = []
    for method, extra in (
        ("rkf78", {"rtol": 1e-12, "atol": 1e-12}),
        ("dp54", {"rtol": 1e-12, "atol": 1e-12}),
        ("rk4", {"step": 30.0}),
        ("scipy-dop853", {"rtol": 1e-12, "atol": 1e-12}),
    ):
        traj = propagate({**cfg0, "integrator": {"method": method, **extra}})
        err = np.linalg.norm(traj.states[:, :3] - truth[:, :3], axis=1) * 1000.0
        step = max(1, len(times) // 150)
        series.append(
            {
                "method": method,
                "orbits": [round(t / period, 4) for t in times[::step]],
                "error_m": [round(float(e), 8) for e in err[::step]],
            }
        )
    return {"series": series}


def covariance_panel() -> dict:
    r0, v0 = elements_to_state(7000.0, 0.01, math.radians(45), 0.0, 0.0, 0.0, MU)
    x0 = np.concatenate([r0, v0])
    p0 = np.diag(np.array([0.5, 0.5, 0.5, 5e-4, 5e-4, 5e-4]) ** 2)
    pts = []
    for dt in np.linspace(300, orbital_period(7000.0, MU), 25):
        out = covariance_study(x0, p0, float(dt), MU, model=None, samples=1500, seed=11)
        cov = np.asarray(out["linear_covariance"])[:3, :3]
        vals = np.sqrt(np.maximum(np.linalg.eigvalsh(cov), 0.0))
        pts.append(
            {
                "minutes": round(dt / 60.0, 2),
                "sigma_max_km": round(float(vals.max()), 4),
                "sigma_min_km": round(float(vals.min()), 4),
                "chi2_inside": round(out["chi2_95_inside_fraction"], 3),
            }
        )
    return {"sigma0_pos_km": 0.5, "points": pts}


def build(use_gmat: bool) -> dict:
    return {
        "generated_by": "scripts/make_orrery_lab.py (rain_atlas.orrery)",
        "epoch_utc": scenarios.EPOCH,
        "earth_radius_km": RE,
        "constants_source": C["source"],
        "orbits": orbit_gallery(),
        "drift": drift_panel(use_gmat),
        "transfer": transfer_panel(),
        "tolerance": tolerance_panel(),
        "propagators": propagator_panel(),
        "covariance": covariance_panel(),
    }


CSS = """
:root{--bg:#070b14;--panel:#0e1526;--ink:#e7edf7;--muted:#8da2c0;--line:#1d2a44;--accent:#4cc9f0}
*{box-sizing:border-box}html,body{margin:0}body{background:var(--bg);color:var(--ink);
font:14px/1.5 "Segoe UI",system-ui,sans-serif}header{padding:18px 22px;border-bottom:1px solid var(--line)}
header h1{margin:0;font-size:19px;letter-spacing:.3px}header p{margin:4px 0 0;color:var(--muted);font-size:12.5px}
.wrap{display:flex;min-height:calc(100vh - 64px)}nav{width:210px;border-right:1px solid var(--line);padding:14px 10px;flex:none}
nav button{display:block;width:100%;text-align:left;background:none;border:1px solid transparent;color:var(--muted);
padding:9px 11px;border-radius:8px;cursor:pointer;font-size:13px;margin-bottom:3px}
nav button:hover{color:var(--ink);background:#111a2e}nav button.on{color:var(--ink);background:#13203a;border-color:var(--line)}
main{flex:1;padding:20px 24px;min-width:0}h2{margin:0 0 6px;font-size:16px}.sub{color:var(--muted);font-size:12.5px;margin:0 0 14px;max-width:70ch}
canvas{background:var(--panel);border:1px solid var(--line);border-radius:10px;max-width:100%}
.legend{display:flex;flex-wrap:wrap;gap:14px;margin:12px 0}.legend span{display:flex;align-items:center;gap:7px;font-size:12.5px;color:var(--muted)}
.sw{width:13px;height:13px;border-radius:3px;display:inline-block}.cards{display:flex;flex-wrap:wrap;gap:12px;margin-top:12px}
.card{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:12px 14px;min-width:150px}
.card b{display:block;font-size:19px}.card small{color:var(--muted)}.foot{color:var(--muted);font-size:12px;margin-top:18px;border-top:1px solid var(--line);padding-top:12px}
.row{display:flex;gap:18px;flex-wrap:wrap;align-items:flex-start}
"""

JS = r"""
'use strict';
var DATA = JSON.parse(document.getElementById('orrery-data').textContent);
var main = document.getElementById('main');
function el(t,a,txt){var e=document.createElement(t);if(a)for(var k in a)e.setAttribute(k,a[k]);if(txt!=null)e.textContent=txt;return e;}
function canvas(w,h){var c=el('canvas');c.width=w;c.height=h;c.style.width=Math.min(w,900)+'px';return c;}
function head(t,s){main.appendChild(el('h2',null,t));var p=el('p',{'class':'sub'},s);main.appendChild(p);}
function legend(items){var d=el('div',{'class':'legend'});items.forEach(function(it){var s=el('span');var sw=el('span',{'class':'sw'});sw.style.background=it.c;s.appendChild(sw);s.appendChild(document.createTextNode(it.t));d.appendChild(s);});main.appendChild(d);}
function cards(items){var d=el('div',{'class':'cards'});items.forEach(function(it){var c=el('div',{'class':'card'});c.appendChild(el('b',null,it.v));c.appendChild(el('small',null,it.k));d.appendChild(c);});main.appendChild(d);}
function foot(t){main.appendChild(el('p',{'class':'foot'},t));}

function orbitView(proj){
  head('Orbit gallery','Earth-centred inertial (MJ2000Eq) trajectories, '+proj.toUpperCase()+' projection. Every point is a numerically propagated state; the grey disc is Earth to scale.');
  var btns=el('div');['xy','xz'].forEach(function(p){var b=el('button',{'class':'nav-sub'},p.toUpperCase());b.style.cssText='margin-right:6px;background:#13203a;color:#e7edf7;border:1px solid #1d2a44;border-radius:7px;padding:5px 12px;cursor:pointer';b.onclick=function(){render('orbits-'+p);};btns.appendChild(b);});main.appendChild(btns);
  var a=(proj==='xy')?[0,1]:[0,2];
  var W=760,H=600,c=canvas(W,H),x=c.getContext('2d');main.appendChild(c);
  var maxr=RE();DATA.orbits.forEach(function(o){o.points.forEach(function(p){maxr=Math.max(maxr,Math.hypot(p[a[0]],p[a[1]]));});});
  var sc=Math.min(W,H)/(2.2*maxr),cx=W/2,cy=H/2;
  function X(p){return cx+p[a[0]]*sc;}function Y(p){return cy-p[a[1]]*sc;}
  x.fillStyle='#223';x.beginPath();x.arc(cx,cy,RE()*sc,0,7);x.fill();
  x.strokeStyle='#2b3a5e';x.beginPath();x.arc(cx,cy,RE()*sc,0,7);x.stroke();
  DATA.orbits.forEach(function(o){x.strokeStyle=o.color;x.lineWidth=1.3;x.beginPath();o.points.forEach(function(p,i){var xx=X(p),yy=Y(p);i?x.lineTo(xx,yy):x.moveTo(xx,yy);});x.stroke();});
  legend(DATA.orbits.map(function(o){return {c:o.color,t:o.title+' ('+o.duration_days+' d)'};}));
  foot('Scale: 1 px = '+(1/sc).toFixed(0)+' km. '+DATA.orbits.length+' scenarios.');
}
function lineChart(title,sub,series,xlabel,ylabel,ylog){
  head(title,sub);
  var W=820,H=460,c=canvas(W,H),x=c.getContext('2d');main.appendChild(c);
  var ml=70,mr=20,mt=16,mb=46,pw=W-ml-mr,ph=H-mt-mb;
  var xs=[],ys=[];series.forEach(function(s){s.x.forEach(function(v){xs.push(v);});s.y.forEach(function(v){ys.push(ylog?Math.max(v,1e-9):v);});});
  var x0=Math.min.apply(null,xs),x1=Math.max.apply(null,xs);
  var y0=ylog?Math.log10(Math.min.apply(null,ys)):Math.min(0,Math.min.apply(null,ys)),y1=ylog?Math.log10(Math.max.apply(null,ys)):Math.max.apply(null,ys);
  if(y1<=y0)y1=y0+1;
  function PX(v){return ml+(v-x0)/(x1-x0||1)*pw;}
  function PY(v){var t=ylog?Math.log10(Math.max(v,1e-9)):v;return mt+ph-(t-y0)/(y1-y0||1)*ph;}
  x.strokeStyle='#1d2a44';x.fillStyle='#8da2c0';x.font='11px sans-serif';
  for(var g=0;g<=5;g++){var gy=mt+ph*g/5;x.beginPath();x.moveTo(ml,gy);x.lineTo(ml+pw,gy);x.stroke();
    var val=y1-(y1-y0)*g/5;x.fillText(ylog?('1e'+Math.round(val)):val.toFixed(2),6,gy+3);}
  x.strokeStyle='#33436a';x.beginPath();x.moveTo(ml,mt);x.lineTo(ml,mt+ph);x.lineTo(ml+pw,mt+ph);x.stroke();
  x.fillText(xlabel,ml+pw/2-20,H-10);x.save();x.translate(14,mt+ph/2+20);x.rotate(-Math.PI/2);x.fillText(ylabel,0,0);x.restore();
  var pal=['#4cc9f0','#f72585','#ffd166','#a0e8af','#c77dff','#ff9f1c'];
  series.forEach(function(s,i){x.strokeStyle=pal[i%pal.length];x.lineWidth=1.6;x.beginPath();s.x.forEach(function(v,j){var xx=PX(v),yy=PY(s.y[j]);j?x.lineTo(xx,yy):x.moveTo(xx,yy);});x.stroke();});
  legend(series.map(function(s,i){return {c:pal[i%pal.length],t:s.label};}));
}
function driftView(){
  if(!DATA.drift.length){head('Predicted vs reference drift','No GMAT reference trajectories are bundled in this build (regenerate with --gmat).');return;}
  lineChart('Predicted vs reference drift','Position difference between ORRERY and the committed NASA GMAT R2026a reference trajectory for each perturbed scenario. Agreement between two independent implementations is code-level consistency, not physical validation.',
    DATA.drift.map(function(d){return {label:d.title+' (max '+d.max_error_m+' m)',x:d.hours,y:d.error_m};}),'elapsed time (hours)','position error vs GMAT (m)',true);
}
function transferView(){
  var t=DATA.transfer;head('Civilian Hohmann transfer','A minimum-energy two-burn transfer from a '+t.r1_km+' km circular parking orbit to GEO ('+t.r2_km+' km), propagated numerically. Burns are instantaneous velocity changes.');
  var W=720,H=640,c=canvas(W,H),x=c.getContext('2d');main.appendChild(c);
  var all=t.park.concat(t.transfer,t.geo),maxr=RE();all.forEach(function(p){maxr=Math.max(maxr,Math.hypot(p[0],p[1]));});
  var sc=Math.min(W,H)/(2.2*maxr),cx=W/2,cy=H/2;
  function P(a,col,wd){x.strokeStyle=col;x.lineWidth=wd;x.beginPath();a.forEach(function(p,i){var xx=cx+p[0]*sc,yy=cy-p[1]*sc;i?x.lineTo(xx,yy):x.moveTo(xx,yy);});x.stroke();}
  x.fillStyle='#223';x.beginPath();x.arc(cx,cy,RE()*sc,0,7);x.fill();
  P(t.park,'#4cc9f0',1.4);P(t.transfer,'#ffd166',1.8);P(t.geo,'#a0e8af',1.4);
  legend([{c:'#4cc9f0',t:'parking orbit'},{c:'#ffd166',t:'transfer ellipse'},{c:'#a0e8af',t:'GEO'}]);
  cards([{k:'Δv₁ (perigee)',v:t.dv1_km_s+' km/s'},{k:'Δv₂ (apogee)',v:t.dv2_km_s+' km/s'},{k:'total Δv',v:t.total_dv_km_s+' km/s'},{k:'time of flight',v:t.tof_hours+' h'}]);
}
function toleranceView(){
  lineChart('Integrator tolerance effect','Position error of '+DATA.tolerance.title+' against a tight (1e-13) reference, for a range of RKF78 tolerances. Looser tolerances take fewer steps but drift sooner.',
    DATA.tolerance.series.map(function(s){return {label:'rtol='+s.tol.toExponential(0)+' ('+s.steps+' steps)',x:s.hours,y:s.error_m};}),'elapsed time (hours)','position error (m)',true);
}
function propagatorView(){
  lineChart('Propagator comparison','Position error against the exact Kepler solution over five orbits for four integrators on the same two-body problem.',
    DATA.propagators.series.map(function(s){return {label:s.method,x:s.orbits,y:s.error_m};}),'orbits','position error vs analytic (m)',true);
}
function covarianceView(){
  var cv=DATA.covariance;head('Covariance uncertainty envelope','Growth of the position 1σ ellipsoid (largest and smallest semi-axis) propagated through the state-transition matrix from a '+cv.sigma0_pos_km+' km initial uncertainty, checked against a Kepler Monte-Carlo cloud (χ² inside fraction near 0.95 means the linear envelope is consistent).');
  lineChart('','',[
    {label:'1σ max semi-axis',x:cv.points.map(function(p){return p.minutes;}),y:cv.points.map(function(p){return p.sigma_max_km;})},
    {label:'1σ min semi-axis',x:cv.points.map(function(p){return p.minutes;}),y:cv.points.map(function(p){return p.sigma_min_km;})}
  ],'elapsed time (minutes)','position 1σ (km)',false);
  var last=cv.points[cv.points.length-1];
  cards([{k:'final 1σ max',v:last.sigma_max_km+' km'},{k:'χ² inside (final)',v:last.chi2_inside}]);
}
function RE(){return DATA.earth_radius_km;}
var VIEWS={'orbits-xy':function(){orbitView('xy');},'orbits-xz':function(){orbitView('xz');},
  drift:driftView,transfer:transferView,tolerance:toleranceView,propagators:propagatorView,covariance:covarianceView};
function render(key){main.innerHTML='';(VIEWS[key]||VIEWS['orbits-xy'])();
  document.querySelectorAll('nav button').forEach(function(b){b.classList.toggle('on',b.dataset.k===key||(key.indexOf('orbits')===0&&b.dataset.k==='orbits-xy'));});}
var NAV=[['orbits-xy','Orbit gallery'],['drift','Predicted vs reference'],['transfer','Hohmann transfer'],['tolerance','Tolerance effect'],['propagators','Propagator comparison'],['covariance','Uncertainty envelope']];
var nav=document.getElementById('nav');
NAV.forEach(function(n){var b=el('button',{'data-k':n[0]},n[1]);b.onclick=function(){render(n[0]);};nav.appendChild(b);});
render('orbits-xy');
"""

TEMPLATE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="{{CSP}}">
<title>ORRERY Celestial Lab</title><style>{{CSS}}</style></head><body>
<header><h1>ORRERY Celestial Lab</h1><p>Offline orbital-dynamics lab for R.A.I.N. Atlas. Every curve is computed by the ORRERY engine; no values are illustrative and nothing loads from the network.</p></header>
<div class="wrap"><nav id="nav"></nav><main id="main"></main></div>
<script id="orrery-data" type="application/json">{{DATA}}</script><script>{{JS}}</script></body></html>
"""


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--gmat", action="store_true", help="include the GMAT drift panel")
    parser.add_argument("--out", type=Path, default=ROOT / "docs" / "orrery-lab.html")
    args = parser.parse_args()
    data = build(args.gmat)
    encoded = (
        json.dumps(data, ensure_ascii=True, allow_nan=False)
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("&", "\\u0026")
    )

    def digest(content: str) -> str:
        return base64.b64encode(hashlib.sha256(content.encode()).digest()).decode()

    csp = (
        f"default-src 'none'; script-src 'sha256-{digest(JS)}'; style-src 'sha256-{digest(CSS)}'; "
        "img-src data:; connect-src 'none'; font-src 'none'; form-action 'none'; base-uri 'none'; object-src 'none'"
    )
    html = (
        TEMPLATE.replace("{{CSP}}", csp)
        .replace("{{CSS}}", CSS)
        .replace("{{DATA}}", encoded)
        .replace("{{JS}}", JS)
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(html, encoding="utf-8", newline="\n")
    print(f"wrote {args.out.relative_to(ROOT)} ({len(html)} bytes, gmat={args.gmat})")


if __name__ == "__main__":
    main()
