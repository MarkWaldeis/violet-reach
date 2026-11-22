// Shared helpers for capture.mjs and bench.mjs: QA server on :5198, real Chrome via Playwright, __vr access.
import { spawn } from "node:child_process";
import { mkdirSync, readFileSync } from "node:fs";
import { createRequire } from "node:module";
import { homedir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

export const REPO = resolve(dirname(fileURLToPath(import.meta.url)), "../..");
export const EXPLORE = join(REPO, "web/explore");
export const PORT = 5198; // 5199 belongs to "Violet Reach starten.bat" — never use it here.
export const ORIGIN = `http://127.0.0.1:${PORT}`;
export const SHOTS = join(homedir(), "devin-screenshots", "violet-reach");
export const VIEWPORT = { width: 1920, height: 1080 };

export const readJSON = (path) => JSON.parse(readFileSync(path, "utf8"));
export const bookmarks = () => readJSON(join(REPO, "world/bookmarks.json"));

export function parseArgs(argv, spec) {
  const out = {};
  for (let i = 0; i < argv.length; i++) {
    const arg = argv[i];
    if (!arg.startsWith("--")) throw new Error(`Unbekanntes Argument: ${arg}`);
    const key = arg.slice(2);
    if (!(key in spec)) throw new Error(`Unbekannte Option --${key} (erlaubt: ${Object.keys(spec).map((k) => `--${k}`).join(", ")})`);
    if (spec[key] === "flag") out[key] = true;
    else {
      const value = argv[++i];
      if (value === undefined || value.startsWith("--")) throw new Error(`--${key} braucht einen Wert`);
      out[key] = value;
    }
  }
  return out;
}

export function timestamp(date = new Date()) {
  const p = (n) => String(n).padStart(2, "0");
  return `${date.getFullYear()}${p(date.getMonth() + 1)}${p(date.getDate())}-${p(date.getHours())}${p(date.getMinutes())}${p(date.getSeconds())}`;
}

export function runDir(name) {
  if (!/^[\w.-]+$/.test(name)) throw new Error(`Ungültiger Laufname: ${name}`);
  const dir = join(SHOTS, name);
  mkdirSync(dir, { recursive: true });
  return dir;
}

async function serverUp() {
  try {
    const response = await fetch(`${ORIGIN}/slice.json`, { signal: AbortSignal.timeout(3000) });
    return response.ok;
  } catch {
    return false;
  }
}

/** Starts the Vite dev server on :5198 unless one already answers; returns a stop() that only stops our own process. */
export async function ensureServer(log = console.log) {
  if (await serverUp()) {
    log(`Prüfserver läuft bereits auf ${ORIGIN}`);
    return { stop: async () => {} };
  }
  log(`Starte Prüfserver auf ${ORIGIN} …`);
  const child = spawn(process.execPath, [join(EXPLORE, "node_modules/vite/bin/vite.js"), "--port", String(PORT), "--strictPort", "--host", "127.0.0.1"], {
    cwd: EXPLORE, stdio: ["ignore", "pipe", "pipe"], windowsHide: true,
    env: { ...process.env, VR_GATE_CACHE_MS: process.env.VR_GATE_CACHE_MS ?? "30000" },
  });
  let output = "";
  child.stdout.on("data", (d) => { output += d; });
  child.stderr.on("data", (d) => { output += d; });
  const exited = new Promise((r) => child.once("exit", r));
  const deadline = Date.now() + 60_000;
  while (!(await serverUp())) {
    if (child.exitCode !== null) throw new Error(`Prüfserver beendet (Port ${PORT} belegt?):\n${output}`);
    if (Date.now() > deadline) { child.kill(); throw new Error(`Prüfserver antwortet nicht nach 60 s:\n${output}`); }
    await new Promise((r) => setTimeout(r, 300));
  }
  return {
    stop: async () => {
      if (child.exitCode !== null) return;
      if (process.platform === "win32") spawn("taskkill", ["/pid", String(child.pid), "/T", "/F"], { stdio: "ignore", windowsHide: true });
      else child.kill();
      await Promise.race([exited, new Promise((r) => setTimeout(r, 5000))]);
    },
  };
}

/** Real Chrome, headed, so the RX 6600 renders (no Playwright browser download). */
export async function launchChrome() {
  const { chromium } = createRequire(join(EXPLORE, "package.json"))("playwright");
  const browser = await chromium.launch({
    channel: "chrome",
    headless: false,
    args: [
      `--window-size=${VIEWPORT.width},${VIEWPORT.height}`, "--window-position=0,0",
      "--enable-unsafe-webgpu", "--ignore-gpu-blocklist", "--force-device-scale-factor=1",
      "--disable-background-timer-throttling", "--disable-renderer-backgrounding", "--disable-backgrounding-occluded-windows",
    ],
  });
  const context = await browser.newContext({ viewport: VIEWPORT, deviceScaleFactor: 1 });
  return { browser, context };
}

export function appURL(query) {
  const q = new URLSearchParams(Object.entries(query).filter(([, v]) => v !== undefined && v !== false).map(([k, v]) => [k, String(v)]));
  return `${ORIGIN}/?${q}`;
}

/** Opens the app and waits for __vr (and optionally __vr.ready) with a clear timeout message. */
export async function openApp(context, query, { ready = true, timeout = 180_000, label = "" } = {}) {
  const page = await context.newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push(String(e)));
  page.on("console", (m) => { if (m.type() === "error") errors.push(m.text()); });
  await page.goto(appURL(query), { waitUntil: "load" });
  try {
    await page.waitForFunction(() => !!window.__vr, null, { timeout: 90_000, polling: 250 });
  } catch {
    const status = await page.locator("#status").textContent().catch(() => "");
    throw new Error(`${label} __vr erscheint nicht (Status: "${status}"; Fehler: ${errors.join(" | ") || "keine"})`);
  }
  if (ready) await waitReady(page, timeout, label);
  return { page, errors };
}

export async function waitReady(page, timeout = 180_000, label = "") {
  try {
    await page.waitForFunction(() => window.__vr?.ready === true, null, { timeout, polling: 200 });
  } catch {
    const s = await page.evaluate(() => { const s = window.__vr?.stats(); return s && { terrain: s.terrain, stableFrames: s.stableFrames, camera: s.camera, assets: s.assets }; }).catch(() => null);
    throw new Error(`${label} __vr.ready nach ${Math.round(timeout / 1000)} s nicht erreicht. Zustand: ${JSON.stringify(s)}`);
  }
}

/** A run is only valid on WebGPU with an AMD adapter, unless it was explicitly started as a WebGL2 run. */
export function validateBackend(stats, webgl) {
  const a = stats.adapter ?? {};
  const text = `${a.vendor} ${a.architecture} ${a.device} ${a.description}`.toLowerCase();
  if (webgl) {
    if (stats.backend !== "WebGL2") return { valid: false, reason: `--webgl angefordert, aber Backend ist ${stats.backend}` };
    return { valid: true, label: "WebGL2 (explizit, nicht vergleichbar mit WebGPU-Messungen)" };
  }
  if (stats.backend !== "WebGPU") return { valid: false, reason: `Backend ist ${stats.backend}, nicht WebGPU` };
  if (!/amd|ati|radeon|rdna/.test(text)) return { valid: false, reason: `Adapter ist nicht die AMD-GPU: ${JSON.stringify(a)}` };
  return { valid: true, label: `WebGPU · ${a.vendor} ${a.architecture} ${a.description}`.trim() };
}

/** Linear interpolation of a key list [{t, ...numbers}] at time t (seconds); yaw is unwrapped along the shortest turn. */
export function interpolateKeys(keys, t) {
  if (t <= keys[0].t) return { ...keys[0] };
  for (let i = 1; i < keys.length; i++) {
    const a = keys[i - 1], b = keys[i];
    if (t <= b.t) {
      const u = (t - a.t) / (b.t - a.t);
      const out = {};
      for (const k of ["x", "z", "agl", "yaw", "pitch"]) {
        let bv = b[k];
        if (k === "yaw") bv = a.yaw + Math.atan2(Math.sin(b.yaw - a.yaw), Math.cos(b.yaw - a.yaw));
        out[k] = a[k] + (bv - a[k]) * u;
      }
      out.t = t;
      return out;
    }
  }
  return { ...keys.at(-1) };
}

export function camParam(b) {
  const r = (n) => Math.round(n * 10000) / 10000;
  return [b.x, b.agl, b.z, b.yaw, b.pitch].map(r).join(",");
}

export function runPython(args, log = console.log) {
  return new Promise((resolvePromise, reject) => {
    const child = spawn("python", args, { cwd: REPO, stdio: ["ignore", "pipe", "pipe"], windowsHide: true });
    let err = "";
    child.stdout.on("data", (d) => log(String(d).trimEnd()));
    child.stderr.on("data", (d) => { err += d; });
    child.on("error", reject);
    child.on("exit", (code) => code === 0 ? resolvePromise() : reject(new Error(`python ${args[0]} Exit ${code}:\n${err}`)));
  });
}
