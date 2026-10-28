const $ = (id) => document.getElementById(id)
const S = { floor: 0, results: {}, state: null, live: null, image: "", settings: {}, look: {}, overrides: {}, draft: null, selected: null, split: 0.5, sizes: {}, targets: null, sync: null }
const RANGE = ["contrast", "saturate", "brightness", "bg_lightness", "bg_chroma", "subtractive_initial"]
const SELECT = ["shading", "choose", "generation_strategy", "bg_strategy"]
// kitty/delta/nvim see the named ANSI slots (templates map kitty colorN to {red} etc.); the fork's
// raw colorN keys are generation order, which is what `walcolor N` prints.
const NAMES = ["black", "red", "green", "yellow", "blue", "magenta", "cyan", "white"]
const ANSI = [...NAMES, ...NAMES.map((n) => `bright_${n}`)]
const EXTRA = ["background", "foreground", "surface0", "surface2", "surface3", "surface5", "subsurface0", "cursor"]

const api = async (path, body) => {
  const res = await fetch(path, body === undefined ? {} : { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) })
  const data = await res.json().catch(() => ({}))
  if (!res.ok) throw new Error(data.error || res.statusText)
  return data
}
const img = (path, w) => `/api/image?path=${encodeURIComponent(path)}&w=${w}`
// Eight-cell palette band (color0-7) from a band array or a colors.json-shaped object.
const bandEl = (p) => {
  const el = Object.assign(document.createElement("span"), { className: "band" })
  const c = Array.isArray(p) ? p : p.band || Array.from({ length: 8 }, (_, i) => p.colors?.[`color${i}`])
  el.append(...c.map((hex) => Object.assign(document.createElement("i"), { style: `background:${hex || "transparent"}` })))
  return el
}
const flat = (c) => ({ ...(c?.colors || {}), ...(c?.surfaces || {}), ...(c?.special || {}) })

async function boot() {
  S.state = await api("/api/state")
  S.live = S.state.live
  fromLive()
  $("where").innerHTML = `${S.state.host} · ${S.state.liveDir}` + (S.state.allowApply ? `<span class="pill live">apply enabled</span>` : `<span class="pill">preview only</span>`)
  $("apply-state").textContent = S.state.allowApply ? "" : "preview only"
  for (const b of [$("apply"), $("apply-top")]) {
    b.disabled = !S.state.allowApply
    b.title = S.state.allowApply ? "Write the draft to the live theme and sync checked apps" : "Preview only: restart the studio with --allow-apply"
  }
  walls()
  bind()
  renderOriginal()
  refreshSync()
  undo()
  await generate()
  if (location.hash === "#compare") $("compare").click()
}

function fromLive() {
  S.theme = null
  S.restore = null
  S.scheme = null
  const live = S.live || {}
  S.image = live.wallpaper || S.state.wallpapers[0]?.path || ""
  S.settings = { ...S.state.defaults, ...(live.settings || {}) }
  if (S.settings.seed != null) S.settings.seed = String(S.settings.seed)
  S.look = { ...S.state.look }
  S.overrides = {}
  S.selected = null
  syncControls()
}

function syncControls() {
  const s = S.settings
  for (const k of RANGE) {
    const fallback = { bg_lightness: 0.03, bg_chroma: 0.02, saturate: 0, brightness: 0 }[k] ?? 0
    $(k).value = s[k] ?? fallback
    showOut(k, s[k])
  }
  for (const k of SELECT) $(k).value = s[k]
  $("seed").value = s.seed ?? ""
  $("blur").value = S.look.blur; showOut("blur", S.look.blur)
  $("tint").value = S.look.tint; showOut("tint", S.look.tint)
  for (const b of $("mode").children) b.classList.toggle("on", (b.dataset.v === "light") === !!s.light)
  markWall()
}

function showOut(id, v) {
  const out = document.querySelector(`output[for=${id}]`)
  if (out) out.textContent = v == null || v === "" ? "auto" : Number(v).toFixed(id.startsWith("bg_") ? 3 : id === "tint" || id === "contrast" ? 2 : 0)
}

function bind() {
  for (const k of RANGE) $(k).addEventListener("input", (e) => { S.settings[k] = Number(e.target.value); showOut(k, S.settings[k]); retune() })
  for (const k of SELECT) $(k).addEventListener("change", (e) => { S.settings[k] = e.target.value; retune() })
  $("seed").addEventListener("change", (e) => { S.settings.seed = e.target.value.replace(/\D/g, ""); retune() })
  $("reseed").onclick = () => { S.settings.seed = seed(); $("seed").value = S.settings.seed; retune(0) }
  $("themes-btn").onclick = toggleThemes
  $("theme-filter").addEventListener("input", renderThemes)
  $("theme-save").onclick = saveTheme
  $("mode").onclick = (e) => { const v = e.target.dataset?.v; if (!v) return; S.settings.light = v === "light"; syncControls(); schedule(0) }
  for (const k of ["blur", "tint"]) $(k).addEventListener("input", (e) => { S.look[k] = Number(e.target.value); showOut(k, S.look[k]); renderDraft() })
  for (const k of RANGE) $(k).addEventListener("input", tracks)
  $("exact").onchange = () => { renderDraft(); renderOriginal() }
  $("chrome").onclick = () => { localStorage.walChrome = localStorage.walChrome === "neutral" ? "tinted" : "neutral"; chrome() }
  for (const k of ["l", "c", "h"]) $(`lch-${k}`).addEventListener("input", () => pin(oklchToHex(+$("lch-l").value, +$("lch-c").value, +$("lch-h").value)))
  $("shuffle-post").onclick = () => shuffle(false)
  $("shuffle-all").onclick = () => shuffle(true)
  $("prev").onclick = () => step(-1)
  $("next").onclick = () => step(1)
  $("random").onclick = () => { const w = S.state.wallpapers; pick(w[Math.floor(Math.random() * w.length)].path) }
  $("live-wall").onclick = () => S.live?.wallpaper && pick(S.live.wallpaper)
  $("revert").onclick = () => { fromLive(); generate() }
  $("compare").onclick = () => { $("compare").classList.toggle("on"); layout() }
  $("slot-color").addEventListener("input", (e) => pin(e.target.value))
  $("slot-hex").addEventListener("change", (e) => /^#[0-9a-f]{6}$/i.test(e.target.value) && pin(e.target.value.toLowerCase()))
  $("slot-clear").onclick = () => { delete S.overrides[S.selected]; schedule(0) }
  $("plan").onclick = plan
  $("apply").onclick = $("apply-top").onclick = apply
  $("probe").onclick = refreshSync
  addEventListener("keydown", (e) => { if (e.key === "c" && !e.repeat && !isField(e.target)) flash(true) })
  addEventListener("keyup", (e) => { if (e.key === "c") flash(false) })
  addEventListener("resize", () => { renderDraft(); renderOriginal(); layout() })
  const split = $("split")
  split.onpointerdown = (e) => {
    split.setPointerCapture(e.pointerId)
    const move = (ev) => { const r = $("stage").getBoundingClientRect(); S.split = Math.min(0.95, Math.max(0.05, (ev.clientX - r.left) / r.width)); layout() }
    split.onpointermove = move
    split.onpointerup = () => { split.onpointermove = null }
  }
}

const isField = (el) => ["INPUT", "SELECT", "TEXTAREA"].includes(el.tagName) && el.type !== "range" && el.type !== "checkbox"
const seed = () => String(Math.floor(Math.random() * 9e17) + 1e17)

function shuffle(all) {
  const r = (a, b) => a + Math.floor(Math.random() * (b - a + 1))
  // Same ranges as `wal --shuffle post|all` (pywal/args.py shuffle_settings).
  Object.assign(S.settings, { brightness: r(-10, 60), saturate: r(-20, 40), shading: Math.random() < 0.5 ? "darken" : "lighten" })
  if (all) {
    const choose = ["random", "ansi", "brightness", "saturation", "ansi-brightness", "ansi-saturation", "ansi-shuffle", "backend"]
    Object.assign(S.settings, { choose: choose[r(0, choose.length - 1)], generation_strategy: Math.random() < 0.7 ? "subtractive" : "iterative", subtractive_initial: r(16, 24) })
  }
  if (String(S.settings.choose).includes("random")) S.settings.seed = seed()
  syncControls()
  retune(0)
}

function walls() {
  $("walls").replaceChildren(...S.state.wallpapers.map((w) => {
    const b = document.createElement("button")
    b.title = w.name
    b.dataset.path = w.path
    b.style.backgroundImage = `url("${img(w.path, 240)}")`
    b.onclick = () => pick(w.path)
    // Solid band = the live cache already holds a generated scheme for this wallpaper.
    if (w.scheme?.colors) b.append(bandEl(w.scheme))
    return b
  }))
  markWall()
}

function markWall() {
  for (const b of $("walls").children) {
    b.classList.toggle("on", b.dataset.path === S.image)
    b.classList.toggle("live", b.dataset.path === S.live?.wallpaper)
  }
  $("wall-name").textContent = S.image.split("/").pop() + (S.theme ? ` · theme ${S.theme.name}` : S.scheme ? " · cached" : "")
  $("walls").querySelector(".on")?.scrollIntoView({ block: "nearest", inline: "nearest" })
}

function step(d) {
  const w = S.state.wallpapers
  const i = w.findIndex((x) => x.path === S.image)
  pick(w[(i + d + w.length) % w.length].path)
}

// The dotfiles `wallpaper` wrapper: --backend colorthief --shading lighten --contrast 1.5, a fresh seed.
const WRAPPER = { shading: "lighten", contrast: 1.5 }

// Generation knobs leave theme mode: the palette comes from the wallpaper again.
function retune(ms) {
  S.restore = null
  if (S.theme || S.scheme) { S.theme = S.scheme = null; S.overrides = {}; markWall() }
  schedule(ms)
}

function pick(path) {
  S.restore = S.scheme = null
  S.image = path
  S.overrides = {}
  if (!$("keep").checked && path !== S.live?.wallpaper) {
    S.settings = { ...S.state.defaults, ...WRAPPER, light: S.settings.light, seed: seed() }
    syncControls()
  }
  markWall()
  schedule(0)
}

let timer, inflight = 0
function schedule(ms = 220) {
  clearTimeout(timer)
  timer = setTimeout(generate, ms)
}

async function generate() {
  const ticket = ++inflight
  $("busy").hidden = false
  try {
    const res = await api("/api/preview", { image: S.image, settings: S.settings, overrides: S.overrides, look: effLook(), theme: S.theme, restore: S.restore, scheme: S.scheme })
    if (ticket !== inflight) return
    S.draft = res.colors
    // A cached scheme brings the settings that generated it; retuning continues from there.
    if (S.scheme) { S.settings = { ...S.state.defaults, ...res.colors.settings }; syncControls() }
    S.settings.seed = String(res.colors.settings.seed)
    $("seed").value = S.settings.seed
    renderDraft()
    outputs(res.outputs)
    slot()
  } catch (e) {
    log(`preview failed: ${e.message}`)
  } finally {
    if (ticket === inflight) $("busy").hidden = true
  }
}

function renderDraft() {
  if (!S.draft) return
  scene($("layer-draft"), flat(S.draft), S.image, effLook(), flat(S.live))
  chrome()
  tracks()
  syncbar()
}

// Darken below the readability floor is held at the floor; preview, plan and Apply all send the held value.
const effLook = () => ({ ...S.look, tint: Math.max(S.look.tint, S.floor) })

function renderOriginal() {
  if (!S.live) return
  scene($("layer-orig"), flat(S.live), S.live.wallpaper, S.state.look, null)
  layout()
}

function layout() {
  const on = $("compare").classList.contains("on")
  const orig = $("layer-orig"), split = $("split")
  orig.hidden = !on && $("flash").hidden
  split.hidden = !on
  if (!on) { orig.style.clipPath = ""; return }
  const w = $("stage").clientWidth
  orig.style.clipPath = `inset(0 ${Math.round(w * (1 - S.split))}px 0 0)`
  split.style.left = `${Math.round(w * S.split)}px`
}

function flash(on) {
  $("flash").hidden = !on
  const orig = $("layer-orig")
  if (on) { orig.hidden = false; orig.style.clipPath = "" } else layout()
}

// One themed desktop: wallpaper, kitty over blurred+darkened glass, Firefox and Editspace beside it.
function scene(layer, c, image, look, was) {
  let root = layer.firstElementChild
  if (!root) {
    layer.innerHTML = `<div class="desk"></div>`
    layer.append($("scene").content.firstElementChild.cloneNode(true))
    root = layer.firstElementChild
  }
  const sc = layer.querySelector(".scene")
  root.style.backgroundImage = `url("${img(image, 1600)}")`
  const bg = c.background, fg = c.foreground
  const term = sc.querySelector(".term")
  term.style.color = fg
  const wp = sc.querySelector(".wp")
  const exact = $("exact").checked
  const ladder = sc.querySelector(".ladder")
  const tint = sc.querySelector(".tint")
  tint.style.background = bg
  tint.style.opacity = look.tint
  const req = (wp.dataset.req = `${image}|${look.blur}|${exact}`)
  sizeOf(image).then(async (size) => {
    // kitty blurs the full-resolution file (sigma = look.blur), then cover-scales it to the window; match that scale here.
    const scale = Math.max(term.clientWidth / size.w, term.clientHeight / size.h)
    const px = look.blur * scale
    if (exact || !CAN_FILTER) {
      wp.style.inset = exact ? "0" : "-60px"
      wp.style.backgroundImage = `url("${exact ? `/api/blur?path=${encodeURIComponent(image)}&sigma=${look.blur}&w=1600` : img(image, 1600)}")`
      wp.style.filter = exact ? "" : `blur(${px.toFixed(2)}px)`
      ladder.style.opacity = 0
      return
    }
    // Blur ladder: pre-blurred levels per wallpaper and pane size; dragging Blur only crossfades opacity.
    const lad = await ladderFor(image, size.w * scale)
    if (wp.dataset.req !== req) return
    const i = Math.max(0, LEVELS.findLastIndex((l) => l <= px)), j = Math.min(LEVELS.length - 1, i + 1)
    const t = j === i ? 0 : Math.min(1, (px - LEVELS[i]) / (LEVELS[j] - LEVELS[i]))
    wp.style.inset = "0"
    wp.style.filter = ""
    wp.style.backgroundImage = `url("${lad.urls[i]}")`
    ladder.style.backgroundImage = `url("${lad.urls[j]}")`
    ladder.style.opacity = t
    if (layer.id === "layer-draft") holdFloor(fg, bg, lad.brightest[i], tint)
  })
  const tabs = sc.querySelectorAll(".tab")
  tabs.forEach((t, i) => { t.style.background = i === 0 ? fg : bg; t.style.color = i === 0 ? bg : fg })
  sc.querySelector(".tty").innerHTML = tty(c)
  fox(sc.querySelector(".fox"), c)
  es(sc.querySelector(".es"), c)
  swatches(sc.querySelector(".swatches"), c, was, layer.id === "layer-draft")
}

const sizes = {}
function sizeOf(path) {
  const known = S.state.wallpapers.find((w) => w.path === path)?.size
  if (known) return Promise.resolve({ w: known[0], h: known[1] })
  return (sizes[path] ??= new Promise((resolve) => {
    const i = new Image()
    i.onload = () => resolve({ w: i.naturalWidth, h: i.naturalHeight })
    i.onerror = () => resolve({ w: 1920, h: 1080 })
    i.src = `/api/image?path=${encodeURIComponent(path)}`
  }))
}

const esc = (s) => s.replace(/[&<>]/g, (m) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" })[m])
function tty(c) {
  const slot = (key) => /^color\d+$/.test(key) ? ANSI[Number(key.slice(5))] : key
  const k = (key, text, extra = "") => `<span data-a="${slot(key)}" style="color:${c[slot(key)]};${extra}">${esc(text)}</span>`
  const b = "font-weight:700"
  const line = (bgc, html) => `<span style="background:${bgc};display:inline-block;min-width:100%">${html}</span>`
  return [
    `${k("color2", "murtaza")}${k("color8", "@")}${k("color6", "mini")} ${k("color4", "~/dotfiles", b)} ${k("color5", "(master)")} ${k("color15", "$")} ls`,
    `${k("color4", "bin/", b)}  ${k("color4", "kitty/", b)}  ${k("color4", "nvim/", b)}  ${k("color2", "install.sh*", b)}  ${k("color6", "walcache@")}  README.md`,
    `${k("color15", "$")} jj log -n3`,
    `${k("color2", "@", b)}  ${k("color13", "lskxs", b)} ${k("color3", "murtaza")} ${k("color6", "2m")}  feat(studio): palette studio`,
    `${k("color8", "◆")}  ${k("color5", "yvlqq")} ${k("color3", "murtaza")} ${k("color6", "6mo")} ${k("color5", "master", b)}  add jjui theme`,
    `${k("color15", "$")} git diff kitty.conf`,
    k("color8", "@@ -86,3 +86,3 @@ background_blur 16"),
    k("color1", "-background_tint 0.95"),
    k("color2", "+background_tint 0.88"),
    `${k("color15", "$")} nvim blend.py`,
    `${k("color8", "  11 ")}${k("color5", "def")} ${k("color4", "blend")}(a, b, t${k("color8", ":")} ${k("color3", "float")} = ${k("color1", "0.5")}):`,
    line(c.surface0 || c.color0, `${k("color11", "  12 ")}    ${k("color8", '"""Mix two colours in OKLab."""', "font-style:italic")}`),
    `${k("color8", "  13 ")}    ${k("color5", "return")} [x ${k("color6", "+")} (y ${k("color6", "-")} x) ${k("color6", "*")} t ${k("color5", "for")} x, y ${k("color5", "in")} ${k("color12", "zip")}(a, b)]`,
    `${k("color9", "E", b)} ${k("color9", "unused import os")}  ${k("color11", "W")} ${k("color11", "line too long")}  ${k("color10", "✓ 14 tests")}`,
    `${k("color15", "$")} colortest`,
    ANSI.slice(0, 8).map((key) => `<span style="background:${c[key]}">${"   "}</span>`).join(" "),
    ANSI.slice(8).map((key) => `<span style="background:${c[key]}">${"   "}</span>`).join(" "),
    ANSI.slice(0, 8).map((key, i) => k(key, ` ${i}  `) + k(ANSI[i + 8], `${i + 8}`.padEnd(3))).join(""),
    `${k("color15", "$")} <span style="background:${c.cursor || c.foreground}">&nbsp;</span>`,
  ].join("\n")
}

// Approximation of pywalfox's default mapping: background, foreground, an accent and lifted surfaces.
function fox(el, c) {
  el.style.background = c.background
  el.style.color = c.foreground
  const tabs = el.querySelectorAll(".fox-tabs span")
  tabs.forEach((t, i) => { t.style.background = i === 0 ? c.surface2 || c.color8 : "transparent"; t.style.color = i === 0 ? c.foreground : c.color15 })
  const url = el.querySelector(".fox-url")
  url.style.background = c.surface0 || c.color0
  url.style.borderTop = `2px solid ${c.color4}`
  url.querySelector("i").style.background = c.color2
}

function es(el, c) {
  const v = themeVars(c)
  if (!v) { el.style.background = "#1e1e2e"; el.style.color = "#cdd6f4"; el.title = "es-app keeps its default theme for light palettes"; return }
  el.title = ""
  el.style.background = v["--base"]
  el.style.color = v["--text"]
  const nav = el.querySelector(".es-nav")
  nav.style.background = v["--crust"]
  nav.style.color = v["--subtext1"]
  nav.querySelectorAll("span").forEach((s, i) => { s.style.background = i === 0 ? v["--surface0"] : ""; s.style.color = i === 0 ? v["--text"] : ""; s.style.borderLeft = `2px solid ${i === 0 ? v["--accent"] : "transparent"}` })
  el.querySelector("em").style.color = v["--accent"]
  el.querySelector(".es-ok").style.color = v["--green"]
  el.querySelector(".es-warn").style.color = v["--yellow"]
}

function swatches(el, c, was, editable) {
  const cell = (key) => {
    const b = document.createElement("button")
    b.className = "sw" + (editable && key === S.selected ? " sel" : "")
    b.style.background = c[key] || "transparent"
    b.style.color = contrast(c[key] || "#000000", "#000000") > 7 ? "#000" : "#fff"
    b.title = `${key} ${c[key] || ""}` + (was && was[key] && was[key] !== c[key] ? `  (live ${was[key]})` : "")
    b.innerHTML = `<span class="k">${ANSI.includes(key) ? ANSI.indexOf(key) : key}</span>`
    if (was && was[key] && was[key] !== c[key]) b.insertAdjacentHTML("afterbegin", `<span class="was" style="background:${was[key]}"></span>`)
    if (editable && S.overrides[key]) b.insertAdjacentHTML("beforeend", `<span class="pin"></span>`)
    if (editable) {
      b.onclick = () => { S.selected = key; renderDraft(); slot() }
      b.onpointerenter = b.onfocus = () => locate(key)
      b.onpointerleave = b.onblur = () => locate()
    }
    return b
  }
  const gap = () => Object.assign(document.createElement("span"), { className: "gap" })
  const row1 = [...ANSI.slice(0, 8).map(cell), gap(), ...EXTRA.slice(0, 4).map(cell)]
  const row2 = [...ANSI.slice(8).map(cell), ...EXTRA.slice(4).map(cell)]
  el.replaceChildren(...row1, ...row2)
}

function slot() {
  const key = S.selected
  $("slot").hidden = !key
  $("lch").hidden = !key
  if (!key || !S.draft) return
  const c = flat(S.draft)
  $("slot-name").textContent = key + (S.overrides[key] ? " · pinned" : "")
  $("slot-color").value = c[key]
  $("slot-hex").value = c[key]
  $("slot-clear").disabled = !S.overrides[key]
  $("lch").hidden = false
  const [L, C, H] = hexToOklch(c[key])
  for (const [k, v, d] of [["l", L, 3], ["c", C, 3], ["h", H, 0]]) {
    if (document.activeElement !== $(`lch-${k}`)) $(`lch-${k}`).value = v
    $(`lch-${k}o`).textContent = v.toFixed(d)
  }
  $("lch-l").style.setProperty("--track", gradient((t) => oklchToHex(t, C, H)))
  $("lch-c").style.setProperty("--track", gradient((t) => oklchToHex(L, t * 0.37, H)))
  $("lch-h").style.setProperty("--track", gradient((t) => oklchToHex(L, Math.max(C, 0.08), t * 360), 18))
}

function pin(hex) {
  S.overrides[S.selected] = hex
  $("slot-hex").value = hex
  schedule(120)
}

function outputs(names) {
  const box = $("outputs")
  box.replaceChildren(...names.filter((n) => !n.endsWith(".png")).map((n) => {
    const b = document.createElement("button")
    b.textContent = n
    b.onclick = async () => {
      const on = b.classList.toggle("on")
      box.querySelectorAll("button").forEach((x) => x !== b && x.classList.remove("on"))
      $("output").hidden = !on
      if (on) $("output").textContent = await (await fetch(`/api/output?name=${encodeURIComponent(n)}`)).text()
    }
    return b
  }))
}

async function refreshSync() {
  S.sync = await api("/api/sync").catch((e) => ({ targets: [], error: e.message }))
  S.targets ??= new Set(S.sync.targets.filter((t) => t.default).map((t) => t.id))
  targets()
}

function targets(results = S.results) {
  S.results = results
  $("targets").replaceChildren(...S.sync.targets.map((t) => {
    const row = document.createElement("label")
    row.className = "target" + (t.available ? "" : " off")
    const r = results[t.id]
    row.innerHTML = `<input type="checkbox" ${S.targets.has(t.id) ? "checked" : ""} ${t.available ? "" : "disabled"}><span class="t">${esc(t.id)}${r ? `<span class="s ${r.status}">${r.status}</span>` : ""}</span><span class="d">${esc(r?.detail || t.detail || "")}</span>`
    row.querySelector("input").onchange = (e) => { e.target.checked ? S.targets.add(t.id) : S.targets.delete(t.id); syncbar() }
    return row
  }))
  syncbar()
}

async function plan() {
  try {
    const p = await api("/api/plan", { targets: [...S.targets], look: effLook() })
    log(planText(p))
    return p
  } catch (e) { log(e.message) }
}

const planText = (p) => [`draft background ${p.background}`, `wallpaper ${p.wallpaper}`, "", ...p.steps.flatMap((s) => [`[${s.target}]`, ...(s.writes || []).map((w) => `  write ${w}`), ...(s.runs || []).map((r) => `  run   ${r}`), ...(s.note ? [`  ${s.note}`] : []), ...(s.backup ? [`  backup ${s.backup}`] : [])])].join("\n")

async function apply() {
  if (!S.state.allowApply) return
  const p = await plan()
  if (!p || !confirm(`Apply the draft to the live theme?\n\n${planText(p)}`)) return
  try {
    const res = await api("/api/apply", { targets: [...S.targets], look: effLook() })
    const by = Object.fromEntries(res.results.map((r) => [r.target, r]))
    S.sync = res.probe
    targets(by)
    log(res.results.map((r) => `${r.target.padEnd(16)} ${r.status.padEnd(9)} ${r.detail || ""}`).join("\n"))
    S.state = await api("/api/state")
    undo()
    S.live = S.state.live
    renderOriginal()
    markWall()
  } catch (e) { log(`apply failed: ${e.message}`) }
}

function log(text) {
  $("log").hidden = false
  $("log").textContent = text
}

// ---- palette-art: chrome tint, tracks, ladder, floor, locate, sync bar ----

const VIVID = ["bright_red", "bright_green", "bright_yellow", "bright_blue", "bright_magenta", "bright_cyan"]
const CHROME = ["--crust", "--mantle", "--base", "--surface0", "--surface1", "--surface2", "--text", "--subtext", "--faint", "--accent", "--ok", "--warn", "--bad"]
// studio.css token names, derived from the draft. Text >= 7:1 and accents >= 4.5:1 on the rail.
function chromeVars(c) {
  const vivid = VIVID.map((k) => c[k]).filter((v) => v && HEX.test(v)).sort((a, b) => hexToOklch(b)[1] - hexToOklch(a)[1])[0]
  if (!vivid || !HEX.test(c.background || "") || luminance(c.background) >= 0.4) return undefined
  const base = mix(c.background, vivid, 0.05)
  const text = readable(c.foreground, base, 7)
  const lift = (k, fallback) => readable(c[k] && HEX.test(c[k]) ? c[k] : fallback, base, 4.5)
  return {
    "--crust": c.background, "--mantle": mix(c.background, vivid, 0.03), "--base": base,
    "--surface0": mix(base, text, 0.1), "--surface1": mix(base, text, 0.16), "--surface2": mix(base, text, 0.24),
    "--text": text, "--subtext": mix(base, text, 0.72), "--faint": mix(base, text, 0.5),
    "--accent": readable(vivid, base, 4.5), "--ok": lift("bright_green", "#00e676"), "--warn": lift("bright_yellow", "#ffcc00"), "--bad": lift("bright_red", "#ff2d55"),
  }
}

function chrome() {
  const root = document.documentElement
  const vars = localStorage.walChrome !== "neutral" && S.draft ? chromeVars(flat(S.draft)) : undefined
  CHROME.forEach((k) => root.style.removeProperty(k))
  root.dataset.chrome = vars ? "tinted" : "neutral"
  $("chrome").textContent = vars ? "Tinted" : "Neutral"
  if (vars) Object.entries(vars).forEach(([k, v]) => root.style.setProperty(k, v))
}

const gradient = (fn, n = 12) => `linear-gradient(90deg, ${Array.from({ length: n + 1 }, (_, i) => fn(i / n)).join(",")})`
// Slider tracks show the range they sweep, painted with the draft's own hues.
function tracks() {
  if (!S.draft) return
  const c = flat(S.draft)
  const [, bC, bH] = hexToOklch(c.background)
  const accent = c.bright_cyan || c.foreground
  const [, , aH] = hexToOklch(accent)
  const set = (id, value) => $(id).style.setProperty("--track", value)
  set("bg_lightness", gradient((t) => oklchToHex(t * 0.4, S.settings.bg_chroma ?? bC, bH)))
  set("bg_chroma", gradient((t) => oklchToHex(Math.max(0.2, S.settings.bg_lightness ?? 0.03), t * 0.15, bH)))
  set("saturate", gradient((t) => oklchToHex(0.66, t * 0.24, aH)))
  set("brightness", gradient((t) => oklchToHex(0.15 + t * 0.8, 0.04, aH)))
  set("contrast", gradient((t) => mix(c.background, c.foreground, 0.2 + t * 0.8)))
  set("blur", `linear-gradient(90deg, ${accent}, ${mix(c.background, accent, 0.3)})`)
  set("tint", `linear-gradient(90deg, ${mix(c.background, c.foreground, 0.35)}, ${c.background})`)
}

const LEVELS = [0, 2, 5, 12, 28, 64] // preview px, at the pane's cover scale
const CAN_FILTER = "filter" in CanvasRenderingContext2D.prototype
const ladders = {}
function ladderFor(image, coverW) {
  return (ladders[`${image}|${Math.round(coverW / 64)}`] ??= (async () => {
    const src = await new Promise((ok, fail) => { const i = new Image(); i.onload = () => ok(i); i.onerror = fail; i.src = img(image, 1600) })
    const w = 640, h = Math.round((w * src.naturalHeight) / src.naturalWidth), k = w / coverW
    const urls = [], brightest = []
    for (const px of LEVELS) {
      const cv = Object.assign(document.createElement("canvas"), { width: w, height: h })
      const ctx = cv.getContext("2d", { willReadFrequently: true })
      const r = px * k
      ctx.filter = r ? `blur(${r}px)` : "none"
      ctx.drawImage(src, -r * 2, -r * 2, w + r * 4, h + r * 4)
      brightest.push(brightestOf(ctx.getImageData(0, 0, w, h).data))
      urls.push(px ? URL.createObjectURL(await new Promise((ok) => cv.toBlob(ok, "image/jpeg", 0.85))) : img(image, 1600))
    }
    return { urls, brightest }
  })())
}
function brightestOf(data) {
  let max = -1, at = 0
  for (let i = 0; i < data.length; i += 16) { const y = 0.2126 * data[i] + 0.7152 * data[i + 1] + 0.0722 * data[i + 2]; if (y > max) { max = y; at = i } }
  return toHex([data[at], data[at + 1], data[at + 2]])
}

// Lowest kitty background_tint that keeps foreground text >= 7:1 over the brightest blurred region.
function holdFloor(fg, bg, brightest, tintEl) {
  let floor = 1
  for (let v = 0; v <= 1; v += 0.01) if (contrast(fg, mix(brightest, bg, v)) >= 7) { floor = v; break }
  S.floor = Math.round(floor * 100) / 100
  const held = S.look.tint < S.floor
  tintEl.style.opacity = Math.max(S.look.tint, S.floor)
  const input = $("tint"), mark = $("floor-mark")
  mark.hidden = S.floor <= 0
  mark.style.setProperty("--floor-x", `${input.offsetLeft + S.floor * input.offsetWidth}px`)
  const out = document.querySelector("output[for=tint]")
  out.textContent = `${Math.max(S.look.tint, S.floor).toFixed(2)}${held ? "↑" : ""}`
  out.title = held ? "held at the readability floor; Apply sends this value" : "kitty background_tint"
}

const hl = document.head.appendChild(document.createElement("style"))
function locate(key) {
  const stage = $("stage")
  if (!key) { delete stage.dataset.hl; hl.textContent = ""; return }
  stage.dataset.hl = key
  hl.textContent = `.stage [data-a]:not([data-a="${key}"]) { opacity: .22 } .stage [data-a="${key}"] { text-decoration: underline 1px; text-underline-offset: 3px }`
}

const SAME = [...ANSI, "background", "foreground", "cursor"]
function syncbar() {
  if (!S.sync) return
  const d = flat(S.draft), l = flat(S.live)
  const dirty = !!S.draft && (S.image !== S.live?.wallpaper || SAME.some((k) => (d[k] || "").toLowerCase() !== (l[k] || "").toLowerCase()) || S.look.tint !== S.state.look.tint || S.look.blur !== S.state.look.blur)
  const state = (t) => !t.available || !S.targets?.has(t.id) ? "off" : ["mismatch", "failed"].includes(S.results[t.id]?.status) ? "bad" : dirty ? "stale" : "live"
  $("syncbar").replaceChildren(...S.sync.targets.map((t) => {
    const el = document.createElement("div")
    el.className = "sb"; el.setAttribute("role", "listitem"); el.dataset.s = state(t)
    el.title = `${t.id}: ${el.dataset.s}${t.detail ? ` · ${t.detail}` : ""}`
    el.innerHTML = `<i></i><span>${esc(t.id)}</span>`
    return el
  }))
  const n = S.sync.targets.filter((t) => state(t) === "stale").length
  $("apply-top").textContent = S.state.allowApply && n ? `Apply · ${n}` : "Apply…"
}

const hexToOklch = (hex) => {
  const [r, g, b] = channels(hex).map((v) => { const c = v / 255; return c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4 })
  const l = Math.cbrt(0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b), m = Math.cbrt(0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b), s = Math.cbrt(0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b)
  const L = 0.2104542553 * l + 0.793617785 * m - 0.0040720468 * s, A = 1.9779984951 * l - 2.428592205 * m + 0.4505937099 * s, B = 0.0259040371 * l + 0.7827717662 * m - 0.808675766 * s
  return [L, Math.hypot(A, B), ((Math.atan2(B, A) * 180) / Math.PI + 360) % 360]
}
// Chroma steps down until the colour fits sRGB, so sliders never clip hue.
const oklchToHex = (L, C, H) => {
  const h = (H * Math.PI) / 180
  for (let c = C, n = 0; n < 24; n++, c *= 0.9) {
    const a = c * Math.cos(h), b = c * Math.sin(h)
    const l = (L + 0.3963377774 * a + 0.2158037573 * b) ** 3, m = (L - 0.1055613458 * a - 0.0638541728 * b) ** 3, s = (L - 0.0894841775 * a - 1.291485548 * b) ** 3
    const rgb = [4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s, -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s, -0.0041960863 * l - 0.7034186147 * m + 1.707614701 * s]
    if (rgb.every((v) => v >= -0.0005 && v <= 1.0005)) return toHex(rgb.map((v) => 255 * (v <= 0.0031308 ? 12.92 * v : 1.055 * Math.max(0, v) ** (1 / 2.4) - 0.055)))
  }
  return toHex([L, L, L].map((v) => 255 * v))
}

// es-app's appearance mapping (packages/es-app/src/appearance.ts themeVars), for a faithful preview.
const HEX = /^#[0-9a-f]{6}$/i
function themeVars(p) {
  const pick = (...keys) => keys.map((key) => p[key]).find((v) => v && HEX.test(v))
  const bg = pick("background", "surface0"), fg = pick("foreground", "bright_white", "white")
  if (!bg || !fg || luminance(bg) >= 0.4) return undefined
  const panel = pick("surface1") ?? mix(bg, fg, 0.05)
  const raised = pick("surface2") ?? mix(bg, fg, 0.12)
  const text = contrast(fg, panel) >= 7 ? fg : "#e6e9ef"
  const accent = (v, fallback) => readable(v ?? fallback, panel, 4.5)
  return {
    "--crust": bg, "--base": panel, "--surface0": raised, "--text": text, "--subtext1": mix(bg, text, 0.72),
    "--green": accent(pick("bright_green", "green"), "#00e676"), "--yellow": accent(pick("bright_yellow", "yellow"), "#ffcc00"),
    "--accent": accent(pick("color2", "cyan", "blue"), "#4a9eff"),
  }
}
const channels = (hex) => [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16))
const toHex = (v) => `#${v.map((x) => Math.round(Math.min(255, Math.max(0, x))).toString(16).padStart(2, "0")).join("")}`
const mix = (a, b, t) => { const x = channels(a), y = channels(b); return toHex(x.map((v, i) => v + (y[i] - v) * t)) }
const luminance = (hex) => { const [r, g, b] = channels(hex).map((v) => { const c = v / 255; return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4 }); return 0.2126 * r + 0.7152 * g + 0.0722 * b }
const contrast = (a, b) => { const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x); return (hi + 0.05) / (lo + 0.05) }
const readable = (color, bg, target) => { for (let s = 0; s <= 10; s++) { const c = mix(color, "#ffffff", s / 10); if (contrast(c, bg) >= target) return c } return "#ffffff" }

boot().catch((e) => log(`studio failed to start: ${e.message}`))

// Themes (`wal --theme`, `--save-theme`) and cached schemes: either replaces the generated palette.
async function toggleThemes() {
  const box = $("themes")
  box.hidden = !box.hidden
  $("themes-btn").classList.toggle("on", !box.hidden)
  if (box.hidden) return
  ;[S.themes, S.schemes] = await Promise.all([api("/api/themes"), api("/api/schemes").catch(() => [])])
  $("theme-save").disabled = $("theme-name").disabled = !S.themes.canSave
  $("theme-name").placeholder = S.themes.canSave ? "save draft as…" : "saving needs --allow-apply"
  renderThemes()
  $("theme-filter").focus()
}

function themeRow(band, name, meta, on, onclick, title) {
  const b = Object.assign(document.createElement("button"), { className: "theme-row", onclick, title: title || name })
  b.classList.toggle("on", on)
  b.append(bandEl(band), Object.assign(document.createElement("span"), { className: "n", textContent: name }), Object.assign(document.createElement("span"), { className: "m", textContent: meta }))
  return b
}

function renderThemes() {
  const q = $("theme-filter").value.trim().toLowerCase()
  const t = S.themes
  const heading = (text) => Object.assign(document.createElement("h3"), { textContent: text })
  const cached = S.schemes.filter((s) => s.wallpaper.toLowerCase().includes(q))
  const schemes = cached.length ? [heading(`Cached · ${cached.length}`), ...cached.map((s) => themeRow(
    s.band, s.wallpaper.split("/").pop(), s.light ? "light" : "dark", S.scheme === s.id,
    () => {
      S.restore = S.theme = null
      S.scheme = s.id
      S.overrides = {}
      // A scheme whose wallpaper is not served here still previews on the current wallpaper.
      if (s.available) S.image = s.wallpaper
      markWall(); renderThemes(); schedule(0)
    },
    s.available ? s.wallpaper : `${s.wallpaper} (not in the wallpaper folder; previews on the current wallpaper)`,
  ))] : []
  const group = (label, source, light, names) => {
    const hits = names.filter((n) => n.toLowerCase().includes(q))
    if (!hits.length) return []
    return [heading(`${label} · ${hits.length}`), ...hits.map((name) => themeRow(
      t.bands[`${source}/${light ? "light" : "dark"}/${name}`] || [], name, "",
      S.theme?.name === name && S.theme?.source === source && !!S.theme?.light === light,
      () => { S.restore = S.scheme = null; S.theme = { source, name, light }; S.overrides = {}; markWall(); renderThemes(); schedule(0) },
    ))]
  }
  $("theme-list").replaceChildren(
    ...schemes,
    ...group("Yours", "user", false, t.user.dark), ...group("Yours · light", "user", true, t.user.light),
    ...group("Dark", "builtin", false, t.builtin.dark), ...group("Light", "builtin", true, t.builtin.light),
  )
}

async function saveTheme() {
  const name = $("theme-name").value.trim()
  if (!name) return
  try {
    const res = await api("/api/themes/save", { name })
    log(`saved ${res.saved}`)
  } catch (e) {
    if (!/exists/.test(e.message) || !confirm(`Replace theme ${name}?`)) return log(e.message)
    log(`saved ${(await api("/api/themes/save", { name, overwrite: true })).saved}`)
  }
  S.themes = await api("/api/themes")
  renderThemes()
}

// Undo: a backup becomes the draft; applying it goes through the same plan, confirm and proofs.
async function undo() {
  const list = await api("/api/backups").catch(() => [])
  $("undo").hidden = !list.length
  $("undo-list").replaceChildren(...list.slice(0, 6).map((b) => {
    const btn = document.createElement("button")
    const t = b.name.replace(/^(\d{4})(\d\d)(\d\d)-(\d\d)(\d\d)(\d\d).*/, "$2-$3 $4:$5:$6")
    btn.innerHTML = `<i style="background:${b.background || "transparent"}"></i>${esc(t)} · ${esc((b.wallpaper || "").split("/").pop())}`
    btn.classList.toggle("on", S.restore === b.name)
    btn.onclick = () => {
      S.restore = b.name
      S.theme = S.scheme = null
      S.overrides = {}
      if (b.wallpaper) S.image = b.wallpaper
      markWall()
      undo()
      schedule(0)
    }
    return btn
  }))
}
