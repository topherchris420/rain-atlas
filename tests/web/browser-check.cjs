// Render an exported offline observatory in Chromium and report what a reviewer sees.
//
// Usage: node browser-check.cjs <index.html> [--assert]
//
// The jsdom tests strip the CSS and Content-Security-Policy; this loads the
// real exported file from file:// with both active, at desktop and phone
// widths, and visits every view. With --assert it exits 1 on any problem.
"use strict";
const path = require("node:path");
const { pathToFileURL } = require("node:url");

const VIEWS = ["observatory", "evidence", "timeline", "skills", "reports", "compose"];
const VIEWPORTS = [
  { width: 1440, height: 900 },
  { width: 390, height: 844 },
];

async function check(file) {
  const { chromium } = require("playwright");
  const browser = await chromium.launch();
  const report = { file, viewports: {}, problems: [] };
  const problem = (where, text) => report.problems.push(`${where}: ${text}`);
  try {
    for (const viewport of VIEWPORTS) {
      const where = `${viewport.width}px`;
      const page = await browser.newPage({ viewport });
      const messages = [];
      const requests = [];
      page.on("console", (m) => messages.push(`${m.type()}: ${m.text()}`));
      page.on("pageerror", (e) => messages.push(`pageerror: ${e.message}`));
      page.on("request", (r) => {
        if (!/^(file|data|blob):/.test(r.url())) requests.push(r.url());
      });
      await page.goto(pathToFileURL(path.resolve(file)).href);
      const csp = await page.getAttribute('meta[http-equiv="Content-Security-Policy"]', "content");
      for (const directive of ["default-src 'none'", "connect-src 'none'", "script-src 'sha256-", "style-src 'sha256-"]) {
        if (!csp || !csp.includes(directive)) problem(where, `CSP lacks ${directive}`);
      }
      // A hash mismatch would block the stylesheet without breaking the script.
      const styled = await page.evaluate(() => getComputedStyle(document.body).backgroundColor);
      if (styled === "rgba(0, 0, 0, 0)") problem(where, "stylesheet blocked or missing");
      const views = {};
      for (const view of VIEWS) {
        await page.evaluate((v) => {
          location.hash = v;
        }, view);
        await page.waitForFunction(
          (v) => document.querySelector('nav [aria-current="page"]')?.hash === "#" + v,
          view,
        );
        const state = await page.evaluate(() => ({
          items: document.querySelector("#view").children.length,
          overflow_px: document.documentElement.scrollWidth - document.documentElement.clientWidth,
          figures: [...document.querySelectorAll("#view img")].map((img) => img.complete && img.naturalWidth > 0),
        }));
        views[view] = state;
        if (!state.items) problem(where, `${view} view rendered nothing`);
        if (state.overflow_px > 0) problem(where, `${view} view overflows horizontally by ${state.overflow_px}px`);
        if (state.figures.includes(false)) problem(where, `${view} view has a figure that did not load`);
      }
      for (const message of messages) problem(where, `console ${message}`);
      for (const url of requests) problem(where, `network request ${url}`);
      // Even when script asks, the page must not reach the network.
      const probe = await page.evaluate(() =>
        fetch("https://example.invalid/").then(
          () => "allowed",
          () => "refused",
        ),
      );
      if (probe !== "refused") problem(where, "a scripted network request was not refused");
      report.viewports[where] = { views, network_probe: probe };
      await page.close();
    }
  } finally {
    await browser.close();
  }
  return report;
}

if (require.main === module) {
  const [file, flag] = process.argv.slice(2);
  if (!file) {
    console.error("usage: node browser-check.cjs <index.html> [--assert]");
    process.exit(2);
  }
  check(file).then(
    (report) => {
      console.log(JSON.stringify(report, null, 2));
      if (flag === "--assert" && report.problems.length) process.exit(1);
    },
    (error) => {
      console.error(error);
      process.exit(2);
    },
  );
}

module.exports = { check };
