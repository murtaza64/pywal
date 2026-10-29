const $ = (id) => document.getElementById(id)
const worker = new Worker("worker.js", { type: "module" })
const pending = new Map()
let nextId = 0
const call = (msg, transfer = []) =>
  new Promise((resolve, reject) => {
    const id = ++nextId
    pending.set(id, { resolve, reject })
    worker.postMessage({ ...msg, id }, transfer)
  })
worker.onmessage = (event) => {
  const job = pending.get(event.data.id)
  pending.delete(event.data.id)
  if (event.data.ok) job.resolve(event.data)
  else job.reject(new Error(event.data.error))
}

const state = { image: null, name: "", mode: "dark", result: null, run: 0, urls: [] }
// Terminal slots as the fork's templates write them (kitty color0 = {black}, color8 = {bright_black}, …).
const BASE = ["black", "red", "green", "yellow", "blue", "magenta", "cyan", "white"]
const ANSI = [...BASE, ...BASE.map((n) => `bright_${n}`)]
const DEFAULTS = { saturate: "0", brightness: "0", contrast: "2", shading: "lighten", choose: "backend", bg_strategy: "backend" }
const FLAGS = { saturate: "--saturate", brightness: "--brightness", contrast: "--contrast", shading: "--shading", choose: "--choose", bg_strategy: "--bg-strategy" }

status("Loading the palette engine (about 15 MB, once)…")
call({ type: "warm" }).then(
  () => status(state.image ? "" : "Engine ready."),
  (err) => status(`Engine failed to load: ${err.message}`, true),
)

$("file").addEventListener("change", () => $("file").files[0] && load($("file").files[0]))
for (const target of [$("drop"), $("stage")]) {
  target.addEventListener("dragover", (e) => {
    e.preventDefault()
    $("drop").classList.add("over")
  })
  target.addEventListener("dragleave", () => $("drop").classList.remove("over"))
  target.addEventListener("drop", (e) => {
    e.preventDefault()
    $("drop").classList.remove("over")
    const file = [...e.dataTransfer.files].find((f) => f.type.startsWith("image/"))
    if (file) load(file)
  })
}
$("view").addEventListener("click", () => $("file").click())

for (const button of $("mode").querySelectorAll("button"))
  button.addEventListener("click", () => {
    state.mode = button.dataset.mode
    for (const b of $("mode").querySelectorAll("button")) b.classList.toggle("on", b === button)
    generate()
  })
for (const id of Object.keys(DEFAULTS)) {
  const el = $(id)
  const out = document.querySelector(`output[for=${id}]`)
  const show = () => out && (out.textContent = id === "contrast" && el.value === "0" ? "off" : el.value)
  show()
  el.addEventListener("input", show)
  el.addEventListener("change", generate)
}
$("seed").addEventListener("change", generate)
$("reroll").addEventListener("click", (e) => {
  e.preventDefault()
  $("seed").value = ""
  generate()
})
$("zip").addEventListener("click", () => state.result && download("wal.zip", state.result.zip))
$("copy-cmd").addEventListener("click", () => navigator.clipboard.writeText($("cmd").textContent))

async function load(file) {
  state.image = await file.arrayBuffer()
  state.name = file.name
  $("wall").src = URL.createObjectURL(file)
  $("term-name").textContent = file.name
  $("drop").hidden = true
  $("view").hidden = false
  generate()
}

async function generate() {
  if (!state.image) return
  const run = ++state.run
  const settings = { ...Object.fromEntries(Object.keys(DEFAULTS).map((k) => [k, value(k)])), light: state.mode === "light" }
  if ($("seed").value.trim()) settings.seed = $("seed").value.trim()
  status("Generating…")
  document.body.classList.add("busy")
  try {
    const bytes = state.image.slice(0)
    const result = await call({ type: "generate", bytes, name: state.name, settings }, [bytes])
    if (run !== state.run) return
    state.result = result
    $("seed").value = result.seed
    render(result, settings)
    status("")
  } catch (err) {
    if (run === state.run) status(`Could not generate a palette: ${err.message}`, true)
  } finally {
    if (run === state.run) document.body.classList.remove("busy")
  }
}

function value(id) {
  const raw = $(id).value
  return $(id).type === "range" ? Number(raw) : raw
}

function render(result, settings) {
  const colors = result.colors.colors
  const roles = JSON.parse(new TextDecoder().decode(result.files["palette.json"])).roles
  const root = document.documentElement.style
  for (const [role, hex] of Object.entries(roles)) root.setProperty(`--${role.replaceAll("_", "-")}`, hex)
  ANSI.forEach((name, i) => root.setProperty(`--c${i}`, colors[name]))
  root.setProperty("--term-bg", result.colors.special.background)
  root.setProperty("--term-fg", result.colors.special.foreground)
  const checks = JSON.parse(new TextDecoder().decode(result.files["palette.json"])).checks
  $("checks").textContent = `text ${checks.text_min.toFixed(1)}:1 · graphics ${checks.graphic_min.toFixed(1)}:1`

  $("cells").replaceChildren(...ANSI.map((name) => cell(colors[name])))
  $("swatches").replaceChildren(
    swatch("background", result.colors.special.background),
    swatch("foreground", result.colors.special.foreground),
    ...ANSI.map((name) => swatch(name.replace("bright_", "br."), colors[name])),
  )

  for (const url of state.urls) URL.revokeObjectURL(url)
  state.urls = []
  const names = Object.keys(result.files).sort((a, b) => a.localeCompare(b))
  $("files").replaceChildren(...names.map((n) => fileRow(n, result.files[n])))
  $("zip").disabled = false
  $("cmd").textContent = command(settings, result.seed)
}

function cell(hex) {
  const el = document.createElement("span")
  el.style.background = hex
  return el
}

function swatch(name, hex) {
  const el = document.createElement("button")
  el.className = "swatch"
  el.title = `Copy ${hex}`
  const chip = document.createElement("i")
  chip.style.background = hex
  const label = document.createElement("span")
  label.textContent = name
  const code = document.createElement("code")
  code.textContent = hex
  el.append(chip, label, code)
  el.addEventListener("click", () => {
    navigator.clipboard.writeText(hex)
    status(`Copied ${hex}`)
  })
  return el
}

function fileRow(name, bytes) {
  const li = document.createElement("li")
  const a = document.createElement("a")
  const url = URL.createObjectURL(new Blob([bytes]))
  state.urls.push(url)
  a.href = url
  a.download = name.split("/").at(-1)
  a.textContent = name
  li.append(a)
  return li
}

function command(settings, seed) {
  const parts = ["wal", "-i", quote(state.name)]
  if (settings.light) parts.push("-l")
  for (const [key, flag] of Object.entries(FLAGS))
    if (String(settings[key]) !== DEFAULTS[key]) parts.push(flag, String(settings[key]))
  parts.push("--seed", seed)
  return parts.join(" ")
}

function quote(s) {
  return /^[\w./-]+$/.test(s) ? s : `'${s.replaceAll("'", "'\\''")}'`
}

function download(name, bytes) {
  const a = document.createElement("a")
  a.href = URL.createObjectURL(new Blob([bytes], { type: "application/zip" }))
  a.download = name
  a.click()
  setTimeout(() => URL.revokeObjectURL(a.href), 1000)
}

function status(text, bad = false) {
  $("status").textContent = text
  $("status").classList.toggle("bad", bad)
}
