import { readFileSync } from "node:fs";
import { test } from "node:test";
import assert from "node:assert/strict";
import { JSDOM, VirtualConsole } from "jsdom";

const base = new URL("../../src/rain_atlas/observatory/", import.meta.url);
const template = readFileSync(new URL("viewer.html", base), "utf8");
const script = readFileSync(new URL("viewer.js", base), "utf8");
const hash = "sha256:" + "a".repeat(64);
const hostile = '<img src=x onerror="window.compromised=true">';
const records = [
  { id: "p1", experiment: "p1", kind: "preregistration", seq: 0, data: { title: "Coupled oscillators", question: "Does locking occur?", hypothesis: "Locking", null_hypothesis: "No locking" } },
  { id: "p2", experiment: "p2", kind: "preregistration", seq: 1, data: { title: "Unfinished control" } },
  { id: "r1", experiment: "p1", kind: "run", seq: 2, data: { status: "ok", purpose: "Primary measurement" } },
  { id: "c1", experiment: "p1", kind: "claim", seq: 3, data: { category: "COMPUTED", statement: hostile, evidence: ["r1"], value: 0.9, unit: "dimensionless" } },
  { id: "ch1", experiment: "p1", kind: "challenge", seq: 4, data: { target: "c1", evidence: ["r1"], outcome: "inconclusive", reasoning: "Insufficient duration" } },
  { id: "v1", experiment: "p1", kind: "verdict", seq: 5, data: { target: "c1", verdict: "unresolved", reasons: ["Insufficient duration"] } },
  { id: "report", experiment: "p1", kind: "report", seq: 6, data: { findings: [{ claims: ["c1"], verdict: "unresolved" }], limitations: ["Synthetic model only"], negative_results: ["Weak coupling did not lock"] } },
];
function viewer(data = records) {
  const errors = [], blobs = [];
  const virtualConsole = new VirtualConsole();
  virtualConsole.on("jsdomError", e => errors.push(e));
  const snapshot = { records: data, figures: [], source_head: hash, integrity: "verified", authenticity: "not authenticated", privacy: "Review free text", skills: [{name:"phase-locking", domain:"resonance", version:"1.0.0", content_hash:hash, trust:"builtin", enabled:true, approved:true, recorded_runs:1, successful_runs:1, test_status:"unknown in snapshot"}] };
  const html = template.replace("{{DATA}}", JSON.stringify(snapshot).replaceAll("<", "\\u003c")).replace("{{JS}}", script).replace("{{CSS}}", "").replace("{{CSP}}", "");
  const dom = new JSDOM(html, {url: "file:///offline/index.html", runScripts: "dangerously", virtualConsole, beforeParse(w) {
    w.Blob = Blob;
    w.URL.createObjectURL = blob => {blobs.push(blob); return "blob:local/" + blobs.length;};
    w.URL.revokeObjectURL = () => {};
    w.fetch = () => { throw new Error("Network request attempted"); };
  }});
  const page = name => {dom.window.location.hash = name; dom.window.dispatchEvent(new dom.window.HashChangeEvent("hashchange"));};
  return {dom, doc:dom.window.document, page, errors, blobs};
}

test("all six views render recorded evidence, filters and provenance", () => {
  const v = viewer();
  try {
    assert.match(v.doc.querySelector("#view").textContent, /Coupled oscillators/);
    for (const name of ["evidence", "timeline", "skills", "reports", "compose", "observatory"]) {
      v.page(name);
      assert.equal(v.doc.querySelector('nav [aria-current="page"]').hash, "#" + name);
      assert.ok(v.doc.querySelector("#view").children.length);
    }
    v.page("evidence");
    assert.match(v.doc.querySelector("#view").textContent, /Primary measurement/);
    assert.match(v.doc.querySelector("#view").textContent, /Insufficient duration/);
    assert.equal(v.doc.querySelectorAll("#view img").length, 0);
    assert.equal(v.dom.window.compromised, undefined);
    v.doc.querySelector("#experiment").value = "p2";
    v.doc.querySelector("#experiment").dispatchEvent(new v.dom.window.Event("change"));
    assert.match(v.doc.querySelector("#view").textContent, /No claims/);
    assert.deepEqual(v.errors, []);
  } finally {v.dom.window.close();}
});

test("composer only downloads an explicit approval-required proposal", async () => {
  const v = viewer();
  try {
    v.page("compose");
    const form = v.doc.querySelector("form");
    for (const input of form.querySelectorAll("textarea")) input.value = "A measurable criterion and control";
    form.dispatchEvent(new v.dom.window.Event("submit", {cancelable:true}));
    assert.match(form.textContent, /Select at least one/);
    form.querySelector('[name="skill"]').checked = true;
    form.dispatchEvent(new v.dom.window.Event("submit", {cancelable:true}));
    const proposal = JSON.parse(await v.blobs.at(-1).text());
    assert.equal(proposal.schema, "atlas.proposal/v1");
    assert.equal(proposal.action, "propose_experiment");
    assert.equal(proposal.approval_required, true);
    assert.equal(proposal.skills[0].content_hash, hash);
    assert.deepEqual(proposal.budget, {max_runs:20, max_seconds:300});
    assert.match(form.textContent, /No execution or approval/);
    assert.deepEqual(v.errors, []);
  } finally {v.dom.window.close();}
});

test("report downloads preserve negative findings and source hash; empty views stay honest", async () => {
  const v = viewer();
  try {
    v.page("reports");
    const markdown = await v.blobs[0].text();
    assert.ok(markdown.includes(hash));
    assert.match(markdown, /Weak coupling did not lock/);
    assert.match(markdown, /Synthetic model only/);
  } finally {v.dom.window.close();}
  const empty = viewer([]);
  try {
    empty.page("reports");
    assert.match(empty.doc.querySelector("#view").textContent, /No completed report/);
    assert.deepEqual(empty.errors, []);
  } finally {empty.dom.window.close();}
});
