"use strict";
const atlas = JSON.parse(document.getElementById("atlas-data").textContent);
const $ = (id) => document.getElementById(id);
const all = atlas.records;
const byId = new Map(all.map((r) => [r.id, r]));
let selectedClaim = null;
const labels = {
  observatory: ["01 / OBSERVATORY", "Make the evidence visible.", "Experiments, independent challenges and the limits of what we can establish."],
  evidence: ["02 / EVIDENCE EXPLORER", "Every claim has a history.", "Trace a finding through its computation, objections, replications and verdict."],
  timeline: ["03 / SCIENTIFIC TIMELINE", "A record of how we know.", "Preregistration precedes execution. Challenges and negative results stay in the record."],
  skills: ["04 / SKILL ATLAS", "Methods you can inspect.", "Executable capabilities, declared assumptions and evidence of their use."],
  reports: ["05 / RESEARCH REPORTS", "Results, with their limits.", "Scientific figures and findings from recorded experiments. Unresolved is a valid outcome."],
  compose: ["06 / EXPERIMENT COMPOSER", "Begin with a testable question.", "Design a local proposal. Download it for inspection and explicit operator approval."]
};
function el(tag, text, className) {
  const node = document.createElement(tag);
  if (text !== undefined && text !== null) node.textContent = String(text);
  if (className) node.className = className;
  return node;
}
function add(parent, ...nodes) { nodes.forEach((n) => parent.append(n)); return parent; }
function tag(text) { return el("span", text, "tag " + (String(text).match(/^[a-z-]+$/) ? text : "")); }
function details(title, data) { const d = el("details"); return add(d, el("summary", title), el("pre", JSON.stringify(data, null, 2))); }
function panel(title) { return add(el("section", null, "panel"), el("h2", title)); }
function linkDownload(text, name, data, mime = "application/json") {
  const a = el("a", text, "download");
  const blob = new Blob([typeof data === "string" ? data : JSON.stringify(data, null, 2)], {type: mime});
  const url = URL.createObjectURL(blob);
  a.href = url; a.download = name;
  a.addEventListener("click", () => setTimeout(() => URL.revokeObjectURL(url), 60000), {once:true});
  return a;
}
function records() {
  const id = $("experiment").value;
  return all.filter((r) => !id || r.experiment === id);
}
function matches(r) { return JSON.stringify(r).toLowerCase().includes($("search").value.toLowerCase()); }
function empty(text) { return el("div", text, "empty"); }
function description(r) { return r.data.statement || r.data.text || r.data.purpose || r.data.title || r.data.method || r.data.name || r.kind; }
function recordRow(r) {
  const row = el("div", null, "row");
  add(row, tag(r.kind), tag(r.data.verdict || r.data.outcome || r.data.status || r.generation), el("p", description(r)), el("small", `#${r.seq} · ${r.at} · ${r.role || "record"}`), details("Inspect projected record · " + r.id.slice(7,19), r));
  return row;
}
function figures(view, id) {
  atlas.figures.filter((f) => !id || f.experiment === id).forEach((f) => {
    const p = panel(f.name.replaceAll("-", " "));
    const img = el("img", null, "figure"); img.src = f.url; img.alt = f.name + "; figure from verified report artifact";
    const a = el("a", "Download figure · PNG", "figure-link"); a.href = f.url; a.download = "atlas-" + f.hash.slice(7,19) + ".png";
    add(view, add(p, img, a, el("div", f.hash, "hash")));
  });
}
function observatory(view, rows) {
  const metric = el("div", null, "metrics");
  [["Recorded runs", rows.filter(r=>r.kind==="run").length], ["Computed claims", rows.filter(r=>r.kind==="claim"&&r.data.category==="COMPUTED").length], ["Supported", rows.filter(r=>r.kind==="verdict"&&r.data.verdict==="supported").length], ["Unresolved / contradicted", rows.filter(r=>r.kind==="verdict"&&r.data.verdict!=="supported").length]].forEach(([label,n])=>add(metric,add(el("div",null,"metric"),el("strong",n),el("span",label))));
  add(view, metric);
  const grid = el("div",null,"grid"), left=el("div"), right=el("div");
  rows.filter(r=>r.kind==="preregistration"&&matches(r)).forEach(r=>{
    const report=rows.find(x=>x.kind==="report"&&x.experiment===r.id), p=panel(r.data.title);
    add(p,tag(report?"reported":"incomplete snapshot"),el("p",r.data.question),el("h3","Preregistered hypothesis"),el("p",r.data.hypothesis),el("small","Null: "+r.data.null_hypothesis),details("Design, controls and acceptance criteria",r.data),el("p",r.id,"hash")); add(left,p);
  });
  figures(left,$("experiment").value);
  const outcome=panel("Evidence status");
  const verdicts=rows.filter(r=>r.kind==="verdict"&&matches(r));
  verdicts.slice(0,12).forEach(r=>{
    const c=byId.get(r.data.target); const row=el("div",null,"row");
    add(row,tag(r.data.verdict),el("p",c?description(c):"Claim unavailable"),el("small",(r.data.reasons||[]).join("; ")));add(outcome,row);
  });
  if(!verdicts.length)add(outcome,el("p","No recorded verdicts in this selection.","muted"));
  add(right,outcome);
  const limits=panel("Limits are part of the result");
  const limitations=[...new Set(rows.filter(r=>r.kind==="report").flatMap(r=>r.data.limitations||[]))];
  limitations.forEach(t=>add(limits,el("p",t,"muted")));
  if(!limitations.length)add(limits,el("p","No report limitations recorded yet. This snapshot does not establish a conclusion.","muted"));
  add(right,limits);add(grid,left,right);add(view,grid);
}
function evidence(view, rows) {
  const claims=rows.filter(r=>r.kind==="claim"&&matches(r));
  if(!claims.length){add(view,empty("No claims match this selection."));return;}
  if(!claims.some(r=>r.id===selectedClaim))selectedClaim=claims[0].id;
  const grid=el("div",null,"grid"), list=panel("Claims / select to trace"), trace=panel("Evidence dependencies");
  claims.forEach(r=>{const b=el("button",null,"claim"+(r.id===selectedClaim?" selected":""));b.type="button";
    const v=rows.find(x=>x.kind==="verdict"&&x.data.target===r.id);add(b,tag(r.data.category),tag(v?.data.verdict||"unresolved"),el("p",r.data.statement));b.addEventListener("click",()=>{selectedClaim=r.id;render();});add(list,b);});
  const claim=byId.get(selectedClaim);add(trace,el("p",claim.data.statement),details("Value, units and uncertainty",{value:claim.data.value,unit:claim.data.unit,uncertainty:claim.data.uncertainty}));
  const flow=el("div",null,"flow");["RUN","CLAIM","CHALLENGE","REPRODUCTION","VERDICT"].forEach((x,i)=>{if(i)add(flow,el("b","→"));add(flow,el("span",x));});add(trace,flow);
  const refs=new Set(claim.data.evidence||[]);
  rows.filter(r=>["challenge","verdict"].includes(r.kind)&&r.data.target===claim.id).forEach(r=>{refs.add(r.id);(r.data.evidence||[]).forEach(x=>refs.add(x));});
  rows.filter(r=>r.kind==="reproduction"&&refs.has(r.data.original_run)).forEach(r=>refs.add(r.id));
  [...refs].map(id=>byId.get(id)).filter(Boolean).sort((a,b)=>a.seq-b.seq).forEach(r=>add(trace,recordRow(r)));
  add(trace,details("Claim provenance",claim));add(view,add(grid,list,trace));
}
function timeline(view, rows) {
  const line=el("div",null,"timeline");
  rows.filter(matches).forEach(r=>{const e=el("article",null,"event");add(e,el("small",`#${r.seq} · ${r.at}`),el("h3",r.data.stage||r.kind),el("p",description(r)),tag(r.role||r.generation),details("Inspect record",r));add(line,e);});
  add(view,line);
}
function skills(view) {
  const grid=el("div",null,"skill-grid");
  atlas.skills.filter(matches).forEach(s=>{const p=panel(s.name);add(p,tag(s.domain),tag("v"+s.version),el("p",s.summary),el("small",`${s.successful_runs}/${s.recorded_runs} recorded runs successful · ${s.examples} declared examples`),el("p",s.test_status,"muted"),details("Inputs and outputs",{inputs:s.inputs,outputs:s.outputs}),details("Dependencies and permissions",{requires:s.requires,permissions:s.permissions,limits:s.limits}),details("Assumptions and failure conditions",s.limitations),el("p",s.content_hash,"hash"));add(grid,p);});add(view,grid);
}
function reports(view, rows) {
  const reports=rows.filter(r=>r.kind==="report"&&matches(r));
  if(!reports.length)add(view,empty("No completed report in this snapshot."));
  reports.forEach(r=>{const p=panel(byId.get(r.experiment)?.data.title||"Research report");
    const pr=byId.get(r.experiment);const lines=["# "+(pr?.data.title||"Research report"),"",pr?.data.question||"", "", "Derived review export; source head: "+atlas.source_head,"", "## Findings"];
    add(p,el("p",r.data.conclusion||"See findings and limitations below."));
    (r.data.findings||[]).forEach(f=>{const c=byId.get(f.claim||(f.claims||[])[0]);const row=el("div",null,"row");add(row,tag(f.verdict),el("p",c?.data.statement||JSON.stringify(f)));add(p,row);lines.push("", "- "+f.verdict+": "+(c?.data.statement||JSON.stringify(f)));});
    ["acceptance","negative_results","limitations"].forEach(key=>{add(p,el("h3",key.replaceAll("_"," ")));const vals=r.data[key]||[];lines.push("","## "+key.replaceAll("_"," "));vals.forEach(x=>{const t=typeof x==="string"?x:JSON.stringify(x);add(p,el("p",t,"muted"));lines.push("",t);});if(!vals.length)add(p,el("small","None recorded in this field."));});
    add(p,linkDownload("Download review report · Markdown","atlas-report.md",lines.join("\n"),"text/markdown"),linkDownload("Download projected evidence · JSON","atlas-review.json",{source_head:atlas.source_head,records:rows.filter(x=>x.experiment===r.experiment)}));add(view,p);});
  figures(view,$("experiment").value);
}
function compose(view) {
  const form=el("form",null,"composer panel");add(form,el("p","This interface only creates a proposal file. It cannot execute skills, approve itself, or contact a runtime.","notice"));
  const fields=[["question","Research question","textarea"],["hypothesis","Testable hypothesis","textarea"],["null_hypothesis","Null hypothesis","textarea"],["controls","Positive and negative controls","textarea"],["criteria","Success thresholds and failure criteria","textarea"],["max_runs","Maximum skill runs","input"],["max_seconds","Maximum compute seconds","input"]];
  fields.forEach(([name,label,type])=>{const id="proposal-"+name, l=el("label",label);l.htmlFor=id;const input=el(type);input.id=id;input.name=name;input.required=true;if(type==="input"){input.type="number";input.min="1";input.max=name==="max_runs"?"200":"3600";input.value=name==="max_runs"?"20":"300";}else input.maxLength=4000;add(form,l,input);});
  const methods=el("fieldset");add(methods,el("legend","Select methods to review"));atlas.skills.filter(s=>s.enabled&&s.approved&&s.trust==="builtin").forEach(s=>{const l=el("label",null,"check"),c=el("input");c.type="checkbox";c.name="skill";c.value=s.name;add(l,c,el("span",s.name+" @ "+s.version));add(methods,l);});add(form,methods);
  const submit=el("button","Prepare proposal download");submit.type="submit";const result=el("div");result.setAttribute("role","status");add(form,submit,result);
  form.addEventListener("submit",e=>{e.preventDefault();const fd=new FormData(form), selected=fd.getAll("skill");result.replaceChildren();if(!selected.length){add(result,el("p","Select at least one method."));return;}
    const proposal={schema:"atlas.proposal/v1",action:"propose_experiment",generation:"human",question:fd.get("question"),hypothesis:fd.get("hypothesis"),null_hypothesis:fd.get("null_hypothesis"),controls:fd.get("controls"),criteria:fd.get("criteria"),skills:selected.map(name=>{const s=atlas.skills.find(s=>s.name===name);return {name:s.name,version:s.version,content_hash:s.content_hash};}),budget:{max_runs:Number(fd.get("max_runs")),max_seconds:Number(fd.get("max_seconds"))},approval_required:true};add(result,el("p","Proposal prepared. No execution or approval has occurred."),linkDownload("Download proposal · JSON","atlas-proposal.json",proposal));});add(view,form);
}
function render() {
  const page=location.hash.slice(1) in labels?location.hash.slice(1):"observatory";
  const [number,title,subtitle]=labels[page];$("section-number").textContent=number;$("title").textContent=title;$("subtitle").textContent=subtitle;
  document.querySelectorAll("nav a").forEach(a=>{a.classList.toggle("active",a.hash==="#"+page);if(a.hash==="#"+page)a.setAttribute("aria-current","page");else a.removeAttribute("aria-current");});
  const view=$("view");view.replaceChildren();({observatory,evidence,timeline,skills,reports,compose})[page](view,records());
}
add($("experiment"),new Option("All recorded experiments",""));all.filter(r=>r.kind==="preregistration").forEach(r=>add($("experiment"),new Option(r.data.title+" · "+r.id.slice(7,15),r.id)));
$("integrity").textContent=atlas.integrity+" · "+atlas.authenticity+" Snapshot: "+(atlas.snapshot_at||"empty");
$("privacy").textContent=atlas.privacy;
$("experiment").addEventListener("change",render);$("search").addEventListener("input",render);window.addEventListener("hashchange",render);render();
