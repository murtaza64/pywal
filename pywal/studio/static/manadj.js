// manaDJ wallpaper theme mapping (wal-palette/1 -> manaDJ tokens, decks, waveform presets, backdrop).
// GENERATED from manadj-wal/ts-v5/walTheme.ts (sha256 3a402740b2c2…, gh#470) with esbuild; do not edit by hand.
// MANADJ_BASE: manaDJ tokens.ts CSS_VARS (surface/text tokens the mapping re-hues).
export const MANADJ_BASE = { '--base': '#1e1e1e', '--mantle': '#181818', '--crust': '#111111', '--void': '#0b0b0f', '--surface0': '#313136', '--surface1': '#45454f', '--surface2': '#58585b', '--overlay0': '#6c7086', '--overlay1': '#7f849c', '--overlay2': '#9399b2', '--text': '#cdd6f4', '--subtext1': '#bac2de', '--subtext0': '#a6adc8' };
const DECKS = ["A", "B", "C", "D"];
const SURFACE_TOKENS = ["--base", "--mantle", "--crust", "--void", "--surface0", "--surface1", "--surface2", "--overlay0", "--overlay1", "--overlay2"];
const TEXT_TOKENS = ["--text", "--subtext1", "--subtext0"];
const SURFACE_CHROMA = 0.018;
const TEXT_CHROMA = 0.03;
const HEX = /^#[0-9a-fA-F]{6}$/;
const SCHEMA = "wal-palette/1";
const ROLES = ["bg", "surface", "raised", "line", "fg", "muted", "faint", "accent", "on_accent", "ok", "warn", "risk", "info", "hl1_bg", "hl2_bg", "hl3_bg", "hl4_bg"];
const HIGHLIGHTS = 8;
function walTheme(doc, base) {
  if (!doc || typeof doc !== "object" || Array.isArray(doc)) return { ok: false, reason: "not a wal-palette document" };
  const d = doc;
  if (d.schema !== SCHEMA) return { ok: false, reason: `unsupported schema ${JSON.stringify(d.schema ?? null)}; expected ${SCHEMA}` };
  if (typeof d.revision !== "string" || !d.revision) return { ok: false, reason: "missing revision" };
  if (d.scheme === "light") return { ok: false, reason: "light palette: manaDJ is dark-only" };
  if (d.scheme !== "dark") return { ok: false, reason: "scheme must be dark or light" };
  if (!d.roles || typeof d.roles !== "object") return { ok: false, reason: "missing roles" };
  const roles = d.roles;
  for (const key of ROLES) {
    if (typeof roles[key] !== "string" || !HEX.test(roles[key])) return { ok: false, reason: `role ${key} is missing or not a #rrggbb colour` };
  }
  const hl = [];
  const raw = d.highlights;
  if (!Array.isArray(raw) || raw.length !== HIGHLIGHTS) return { ok: false, reason: `highlights must be ${HIGHLIGHTS} #rrggbb colours` };
  for (let i = 0; i < HIGHLIGHTS; i++) {
    const h = raw[i];
    if (typeof h !== "string" || !HEX.test(h)) return { ok: false, reason: `highlights must be ${HIGHLIGHTS} #rrggbb colours` };
    hl.push(h);
  }
  const bgHue = hexToOklch(roles.bg)[2];
  const fgHue = hexToOklch(roles.fg)[2];
  const vars = {};
  for (const name of SURFACE_TOKENS) if (HEX.test(base[name] ?? "")) vars[name] = rehue(base[name], bgHue, SURFACE_CHROMA);
  for (const name of TEXT_TOKENS) if (HEX.test(base[name] ?? "")) vars[name] = rehue(base[name], fgHue, TEXT_CHROMA);
  const accent = vivid(hexToOklch(roles.accent)[2], 0.62, 0.78);
  vars["--accent"] = accent;
  vars["--accent-rgb"] = rgbTriplet(accent);
  const terminal = d.terminal && typeof d.terminal === "object" && !Array.isArray(d.terminal) ? d.terminal : {};
  const sources = [
    ...hl.map((hex, i) => [`hl${i + 1}`, hex]),
    ...TERMINAL_KEYS.filter((k) => typeof terminal[k] === "string" && HEX.test(terminal[k])).map((k) => [`terminal.${k}`, terminal[k]])
  ];
  const { decks: deckProposal, report: deckReport } = pickDecks(sources, hexToOklch(accent)[2]);
  const waveformPresets = presets(sources, accent, deckProposal, base["--void"] ?? WAVE_BG);
  const backdrop = backdropProposal(vars, waveformPresets);
  return { ok: true, revision: d.revision, vars, deckProposal, deckReport, waveformPresets, backdrop };
}
const DEFAULT_DECKS = { A: "#00e5ff", B: "#ff2d95", C: "#ff7a00", D: "#8f4dff" };
const SUCCESS = "#00e676";
const ROUTINE_ACCENT = "#a8ff00";
const DECK_MIN_GAP = 60;
const ACCENT_CLEARANCE = 30;
const SUCCESS_CLEARANCE = 25;
const ROUTINE_CLEARANCE = 25;
const MIN_SOURCE_CHROMA = 0.06;
const TERMINAL_KEYS = ["red", "green", "yellow", "blue", "magenta", "cyan", "bright_red", "bright_green", "bright_yellow", "bright_blue", "bright_magenta", "bright_cyan"];
const hueDist = (a, b) => {
  const x = Math.abs(a - b) % 360;
  return x > 180 ? 360 - x : x;
};
const minGapOf = (hues) => {
  let m = 360;
  for (let i = 0; i < hues.length; i++) for (let j = i + 1; j < hues.length; j++) m = Math.min(m, hueDist(hues[i], hues[j]));
  return m;
};
function pickDecks(sources, accentHue) {
  const successHue = hexToOklch(SUCCESS)[2];
  const routineHue = hexToOklch(ROUTINE_ACCENT)[2];
  const allowed = (h) => hueDist(h, accentHue) >= ACCENT_CLEARANCE && hueDist(h, successHue) >= SUCCESS_CLEARANCE && hueDist(h, routineHue) >= ROUTINE_CLEARANCE;
  const cands = [];
  for (const [src, hex] of sources) {
    const [, C, H] = hexToOklch(hex);
    if (C < MIN_SOURCE_CHROMA || !allowed(H) || cands.some((c) => hueDist(c.hue, H) < 8)) continue;
    cands.push({ src, hue: H });
  }
  const grid = Array.from({ length: 180 }, (_, i) => i * 2).filter(allowed);
  const fill = (hues) => {
    const m = 4 - hues.length;
    if (m === 0) return [...hues];
    let lo = 0;
    let hi = 180;
    let best2 = place(hues, m, grid, 0) ?? [];
    while (hi - lo > 0.5) {
      const d = (lo + hi) / 2;
      const p = place(hues, m, grid, d);
      if (p) {
        lo = d;
        best2 = p;
      } else hi = d;
    }
    return [...hues, ...best2];
  };
  let best = null;
  const better = (a, b) => {
    if (!b) return true;
    const okA = a.gap >= DECK_MIN_GAP, okB = b.gap >= DECK_MIN_GAP;
    if (okA !== okB) return okA;
    if (okA && a.idx.length !== b.idx.length) return a.idx.length > b.idx.length;
    if (!okA && Math.abs(a.gap - b.gap) > 1e-9) return a.gap > b.gap;
    if (a.idx.length !== b.idx.length) return a.idx.length > b.idx.length;
    return a.idx.reduce((s, x) => s + x, 0) < b.idx.reduce((s, x) => s + x, 0);
  };
  const n = cands.length;
  const visit = (start, idx) => {
    const hues = fill(idx.map((i) => cands[i].hue));
    const p = { idx, hues, gap: minGapOf(hues) };
    if (better(p, best)) best = p;
    if (idx.length === 4) return;
    for (let i = start; i < n; i++) visit(i + 1, [...idx, i]);
  };
  visit(0, []);
  const pick = best;
  const srcs = pick.hues.map((_, i) => i < pick.idx.length ? cands[pick.idx[i]].src : "synthesized");
  const homes = DECKS.map((k) => hexToOklch(DEFAULT_DECKS[k])[2]);
  let order = [0, 1, 2, 3];
  let cost = Infinity;
  for (const perm of permutations([0, 1, 2, 3])) {
    const c = perm.reduce((s, h, deck) => s + hueDist(pick.hues[h], homes[deck]), 0);
    if (c < cost) {
      cost = c;
      order = perm;
    }
  }
  const decks = Object.fromEntries(DECKS.map((k, i) => [k, vivid(pick.hues[order[i]], 0.6, 0.88)]));
  const source = Object.fromEntries(DECKS.map((k, i) => [k, srcs[order[i]]]));
  return { decks, report: { source, minGap: Math.round(pick.gap * 10) / 10, cvdMin: cvdMinDistance(Object.values(decks)) } };
}
function place(fixed, m, grid, d) {
  const ok = grid.filter((h) => fixed.every((f) => hueDist(f, h) >= d));
  const pack = (start, wrap) => {
    const offs = fixed.map((f) => (f - start + 360) % 360);
    const out = [];
    let last = -Infinity;
    for (const off of ok.map((h) => (h - start + 360) % 360).sort((x, y) => x - y)) {
      if (offs.some((f) => f > last && f < off)) last = -Infinity;
      if (off - last < d) continue;
      out.push(off);
      last = off;
      if (out.length === m) break;
    }
    if (out.length < m || wrap && 360 - out[m - 1] < d) return null;
    return out.map((off) => (off + start) % 360);
  };
  if (fixed.length) return pack(fixed[0], false);
  for (const s of ok) {
    const p = pack(s, true);
    if (p) return p;
  }
  return null;
}
function permutations(xs) {
  if (xs.length <= 1) return [xs];
  return xs.flatMap((x, i) => permutations([...xs.slice(0, i), ...xs.slice(i + 1)]).map((p) => [x, ...p]));
}
const CVD = [
  [[0.152286, 1.052583, -0.204868], [0.114503, 0.786281, 0.099216], [-3882e-6, -0.048116, 1.051998]],
  [[0.367322, 0.860646, -0.227968], [0.280085, 0.672501, 0.047413], [-0.01182, 0.04294, 0.968881]],
  [[1.255528, -0.076749, -0.178779], [-0.078411, 0.930809, 0.147602], [4733e-6, 0.691367, 0.3039]]
];
function linToOklab([r, g, b]) {
  const l = Math.cbrt(Math.max(0, 0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b));
  const m = Math.cbrt(Math.max(0, 0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b));
  const s = Math.cbrt(Math.max(0, 0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b));
  return [0.2104542553 * l + 0.793617785 * m - 0.0040720468 * s, 1.9779984951 * l - 2.428592205 * m + 0.4505937099 * s, 0.0259040371 * l + 0.7827717662 * m - 0.808675766 * s];
}
function cvdMinDistance(hexes) {
  let min = Infinity;
  for (const M of CVD) {
    const labs = hexes.map((hex) => {
      const c = [1, 3, 5].map((i) => toLinear(parseInt(hex.slice(i, i + 2), 16) / 255));
      return linToOklab(M.map((row) => Math.min(1, Math.max(0, row[0] * c[0] + row[1] * c[1] + row[2] * c[2]))));
    });
    for (let i = 0; i < labs.length; i++) for (let j = i + 1; j < labs.length; j++) min = Math.min(min, Math.hypot(labs[i][0] - labs[j][0], labs[i][1] - labs[j][1], labs[i][2] - labs[j][2]));
  }
  return Math.round(min * 1e3) / 1e3;
}
const WAVE_BG = "#0b0b0f";
const BAND_MIN_CONTRAST = 3;
const hexToRgb = (hex) => [1, 3, 5].map((i) => Math.round(parseInt(hex.slice(i, i + 2), 16) / 255 * 1e3) / 1e3);
function wallpaperTriad(sources) {
  const hues = sources.map(([, hex]) => hexToOklch(hex)).filter(([, C]) => C >= MIN_SOURCE_CHROMA).map(([, , H]) => H);
  const red = hexToOklch("#ff1a1a")[2];
  let bestRot = 0;
  let bestCost = Infinity;
  for (let rot = -50; rot <= 50; rot += 2) {
    const triad = [0, 1, 2].map((k) => red + rot + k * 120);
    const cost = triad.reduce((s, t) => s + (hues.length ? Math.min(...hues.map((h) => hueDist(h, t))) : 0), 0) + Math.abs(rot) * 0.2;
    if (cost < bestCost) {
      bestCost = cost;
      bestRot = rot;
    }
  }
  return [0, 1, 2].map((k) => hexToRgb(vivid((red + bestRot + k * 120 + 360) % 360, 0.62, 0.86)));
}
function hueLayers(hex) {
  const [, , H] = hexToOklch(hex);
  const low = oklchToHex(0.55, maxChroma(0.55, H) * 0.95, H);
  const mid = vivid(H, 0.7, 0.85);
  const high = oklchToHex(0.95, Math.min(0.05, maxChroma(0.95, H)), H);
  return [hexToRgb(low), hexToRgb(mid), hexToRgb(high)];
}
function presets(sources, accent, decks, waveBg) {
  const out = [
    { id: "default", name: "manaDJ default", colors: null },
    { id: "wallpaper", name: "Wallpaper triad", colors: wallpaperTriad(sources) },
    { id: "deck", name: "Deck-tinted", colors: hueLayers(accent), perDeck: Object.fromEntries(DECKS.map((k) => [k, hueLayers(decks[k])])) },
    { id: "accent", name: "Mono accent", colors: hueLayers(accent) }
  ];
  const lift = (c) => {
    let hex = rgbToHex(c);
    for (let i = 0; i < 40 && contrast(hex, waveBg) < BAND_MIN_CONTRAST; i++) {
      const [L, C, H] = hexToOklch(hex);
      hex = oklchToHex(L + 0.01, Math.min(C, maxChroma(L + 0.01, H)), H);
    }
    return hexToRgb(hex);
  };
  for (const p of out) {
    if (p.colors) p.colors = p.colors.map(lift);
    if (p.perDeck) for (const k of DECKS) p.perDeck[k] = p.perDeck[k].map(lift);
  }
  return out;
}
const BACKDROP_BLUR = { library: 24, decks: 32, waveforms: 40 };
function backdropDim(fg, ratio, brightest = "#ffffff") {
  const [r, g, b] = hexToRgb(brightest);
  const at = (dim) => rgbToHex([r * (1 - dim), g * (1 - dim), b * (1 - dim)]);
  if (contrast(fg, at(1)) < ratio) return 1;
  if (contrast(fg, at(0)) >= ratio) return 0;
  let lo = 0;
  let hi = 1;
  for (let i = 0; i < 30; i++) {
    const mid = (lo + hi) / 2;
    if (contrast(fg, at(mid)) >= ratio) hi = mid;
    else lo = mid;
  }
  return Math.ceil(hi * 1e3) / 1e3;
}
function backdropProposal(vars, waveformPresets, brightest = "#ffffff") {
  const text = Math.max(backdropDim(vars["--text"], 7, brightest), vars["--subtext0"] ? backdropDim(vars["--subtext0"], 4.5, brightest) : 0);
  const bands = waveformPresets.flatMap((p) => [...p.colors ?? [], ...Object.values(p.perDeck ?? {}).flat()]).map(rgbToHex);
  const wave = Math.max(text, ...bands.map((hex) => backdropDim(hex, BAND_MIN_CONTRAST, brightest)));
  const round = (x) => Math.min(1, Math.ceil(x * 100) / 100);
  return {
    overlay: "#000000",
    scopes: {
      library: { blur: BACKDROP_BLUR.library, dim: round(text), dimFloor: text, needsRenderer: false },
      decks: { blur: BACKDROP_BLUR.decks, dim: round(text), dimFloor: text, needsRenderer: false },
      waveforms: { blur: BACKDROP_BLUR.waveforms, dim: round(wave), dimFloor: wave, needsRenderer: true }
    }
  };
}
const rgbToHex = (c) => "#" + c.map((v) => Math.round(Math.min(1, Math.max(0, v)) * 255).toString(16).padStart(2, "0")).join("");
const lum = (hex) => {
  const [r, g, b] = [1, 3, 5].map((i) => toLinear(parseInt(hex.slice(i, i + 2), 16) / 255));
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
};
const contrast = (a, b) => {
  const [x, y] = [lum(a), lum(b)].sort((p, q) => q - p);
  return (x + 0.05) / (y + 0.05);
};
function deckVars(decks) {
  return Object.fromEntries(Object.entries(decks).flatMap(([deck, hex]) => [[`--deck-${deck.toLowerCase()}`, hex], [`--deck-${deck.toLowerCase()}-rgb`, rgbTriplet(hex)]]));
}
const toLinear = (u) => u <= 0.04045 ? u / 12.92 : ((u + 0.055) / 1.055) ** 2.4;
const toGamma = (u) => u <= 31308e-7 ? 12.92 * u : 1.055 * u ** (1 / 2.4) - 0.055;
function hexToOklch(hex) {
  const [r, g, b] = [1, 3, 5].map((i) => toLinear(parseInt(hex.slice(i, i + 2), 16) / 255));
  const l = Math.cbrt(0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b);
  const m = Math.cbrt(0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b);
  const s = Math.cbrt(0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b);
  const L = 0.2104542553 * l + 0.793617785 * m - 0.0040720468 * s;
  const A = 1.9779984951 * l - 2.428592205 * m + 0.4505937099 * s;
  const B = 0.0259040371 * l + 0.7827717662 * m - 0.808675766 * s;
  const H = Math.atan2(B, A) * 180 / Math.PI;
  return [L, Math.hypot(A, B), H < 0 ? H + 360 : H];
}
function oklchToLinear(L, C, H) {
  const A = C * Math.cos(H * Math.PI / 180);
  const B = C * Math.sin(H * Math.PI / 180);
  const l = (L + 0.3963377774 * A + 0.2158037573 * B) ** 3;
  const m = (L - 0.1055613458 * A - 0.0638541728 * B) ** 3;
  const s = (L - 0.0894841775 * A - 1.291485548 * B) ** 3;
  return [
    4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s,
    -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s,
    -0.0041960863 * l - 0.7034186147 * m + 1.707614701 * s
  ];
}
const inGamut = (L, C, H) => oklchToLinear(L, C, H).every((v) => v >= -1e-4 && v <= 1 + 1e-4);
function oklchToHex(L, C, H) {
  return "#" + oklchToLinear(L, C, H).map((v) => Math.round(Math.min(1, Math.max(0, toGamma(Math.min(1, Math.max(0, v))))) * 255).toString(16).padStart(2, "0")).join("");
}
function maxChroma(L, H) {
  let lo = 0;
  let hi = 0.4;
  for (let i = 0; i < 30; i++) {
    const mid = (lo + hi) / 2;
    if (inGamut(L, mid, H)) lo = mid;
    else hi = mid;
  }
  return lo;
}
function vivid(H, lo, hi) {
  let best = lo;
  for (let i = 0; i <= 40; i++) {
    const L = lo + i * (hi - lo) / 40;
    if (maxChroma(L, H) > maxChroma(best, H)) best = L;
  }
  return oklchToHex(best, maxChroma(best, H) * 0.98, H);
}
function rehue(tokenHex, hue, cap) {
  const [L, C] = hexToOklch(tokenHex);
  return oklchToHex(L, Math.min(cap, Math.max(C, cap * 0.6)), hue);
}
function rgbTriplet(hex) {
  const v = parseInt(hex.slice(1), 16);
  return `${v >> 16 & 255}, ${v >> 8 & 255}, ${v & 255}`;
}
export {
  ACCENT_CLEARANCE,
  BACKDROP_BLUR,
  BAND_MIN_CONTRAST,
  DECKS,
  DECK_MIN_GAP,
  DEFAULT_DECKS,
  HIGHLIGHTS,
  ROLES,
  ROUTINE_ACCENT,
  ROUTINE_CLEARANCE,
  SCHEMA,
  SUCCESS,
  SUCCESS_CLEARANCE,
  SURFACE_CHROMA,
  SURFACE_TOKENS,
  TEXT_CHROMA,
  TEXT_TOKENS,
  WAVE_BG,
  backdropDim,
  backdropProposal,
  contrast,
  cvdMinDistance,
  deckVars,
  hexToOklch,
  hexToRgb,
  hueDist,
  maxChroma,
  oklchToHex,
  vivid,
  walTheme
};
