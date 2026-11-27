#!/usr/bin/env node
import { mkdirSync } from "node:fs";
import { resolve, dirname } from "node:path";
import { fileURLToPath } from "node:url";
import puppeteer from "puppeteer-core";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const outDir = resolve(root, "../website-shots");
const url = process.env.AETHENS_SITE_URL ?? "http://127.0.0.1:4321";
const executablePath = process.env.CHROME_PATH ?? "/usr/bin/google-chrome";

mkdirSync(outDir, { recursive: true });

const browser = await puppeteer.launch({
  executablePath,
  headless: true,
  args: ["--no-sandbox", "--disable-dev-shm-usage", "--font-render-hinting=none"],
});

async function shot(name, { width, height, deviceScaleFactor = 1 }) {
  const page = await browser.newPage();
  await page.setViewport({ width, height, deviceScaleFactor });
  await page.emulateMediaFeatures([{ name: "prefers-reduced-motion", value: "reduce" }]);
  const response = await page.goto(url, { waitUntil: "networkidle0", timeout: 60_000 });
  const status = response ? response.status() : 0;
  if (!response || status >= 400) {
    throw new Error(`GET ${url} failed: ${status || "no response"}`);
  }
  await page.evaluate(() => document.fonts.ready);
  const dest = resolve(outDir, name);
  await page.screenshot({ path: dest, fullPage: true, type: "png" });
  await page.close();
  console.log(`Wrote ${dest}`);
}

try {
  await shot("desktop.png", { width: 1440, height: 900, deviceScaleFactor: 1 });
  await shot("mobile.png", { width: 390, height: 844, deviceScaleFactor: 2 });
} finally {
  await browser.close();
}
