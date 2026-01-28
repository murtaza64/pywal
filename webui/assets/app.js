const $ = (id) => document.getElementById(id)

const state = {
  imagePath: null,
  lastResult: null,
  debounce: null,
}

function hexToRgb(hex) {
  const h = hex.replace('#', '')
  const r = parseInt(h.slice(0, 2), 16)
  const g = parseInt(h.slice(2, 4), 16)
  const b = parseInt(h.slice(4, 6), 16)
  return { r, g, b }
}

function relLum(hex) {
  const { r, g, b } = hexToRgb(hex)
  const srgb = [r, g, b].map((v) => v / 255)
  const lin = srgb.map((u) => (u <= 0.04045 ? u / 12.92 : Math.pow((u + 0.055) / 1.055, 2.4)))
  return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]
}

function contrastRatio(bg, fg) {
  const L1 = relLum(bg)
  const L2 = relLum(fg)
  const a = Math.max(L1, L2)
  const b = Math.min(L1, L2)
  return (a + 0.05) / (b + 0.05)
}

function setReadouts() {
  $('contrast-val').textContent = $('contrast').value
  $('brightness-val').textContent = $('brightness').value
  $('saturate-val').textContent = $('saturate').value
  $('bg_chroma_floor-val').textContent = $('bg_chroma_floor').value
  $('greyish_chroma_threshold-val').textContent = $('greyish_chroma_threshold').value
}

function paramsFromUI() {
  return {
    light: $('light').checked,
    shading: $('shading').value,
    generation_strategy: $('generation_strategy').value,
    subtractive_initial: parseInt($('subtractive_initial').value || '16', 10),
    choose: $('choose').value,
    shuffle: $('shuffle').checked,
    seed: $('seed').value === '' ? null : parseInt($('seed').value, 10),
    contrast: parseFloat($('contrast').value),
    brightness: parseFloat($('brightness').value),
    saturate: parseFloat($('saturate').value),
    bg_chroma_floor: parseFloat($('bg_chroma_floor').value),
    greyish_chroma_threshold: parseFloat($('greyish_chroma_threshold').value),
  }
}

async function api(path, opts) {
  const res = await fetch(path, opts)
  if (!res.ok) {
    const text = await res.text()
    throw new Error(`${res.status} ${res.statusText}: ${text}`)
  }
  return await res.json()
}

function renderSwatches(container, items, bgHex) {
  container.innerHTML = ''
  for (const it of items) {
    const hex = it.hex
    const name = it.name
    const el = document.createElement('div')
    el.className = 'swatch'
    el.style.background = bgHex ? bgHex : hex
    el.style.color = bgHex ? hex : '#111111'
    el.textContent = name ? `${name} ${hex}` : hex
    if (bgHex) {
      const r = contrastRatio(bgHex, hex)
      el.title = `contrast: ${r.toFixed(2)}`
    }
    container.appendChild(el)
  }
}

function renderStrip8x2(container, a, b) {
  container.innerHTML = ''
  const cells = [...a, ...b]
  for (const hex of cells) {
    const el = document.createElement('div')
    el.style.background = hex
    container.appendChild(el)
  }
}

function renderAccentColumn(container, bgHex, entries) {
  container.innerHTML = ''
  const header = document.createElement('div')
  header.className = 'accentlabel'
  header.textContent = `text on ${bgHex}`
  container.appendChild(header)

  for (const e of entries) {
    const item = document.createElement('div')
    item.className = 'accentitem'
    item.style.color = e.color
    item.textContent = e.name
    item.title = `contrast: ${contrastRatio(bgHex, e.color).toFixed(2)} (${e.color})`
    container.appendChild(item)
  }
}

function renderSurfaces(container, bgHex, items) {
  container.innerHTML = ''
  for (const it of items) {
    const el = document.createElement('div')
    el.className = 'surface'
    el.style.background = it.hex

    const label = document.createElement('div')
    label.className = 'surface__label'
    label.style.color = bgHex
    label.textContent = `${it.name} ${it.hex}`
    label.title = `contrast: ${contrastRatio(it.hex, bgHex).toFixed(2)}`

    el.appendChild(label)
    container.appendChild(el)
  }
}

function renderGrid(container, items, bgHex) {
  container.innerHTML = ''
  for (const it of items) {
    const el = document.createElement('div')
    el.className = 'cell'
    el.style.background = bgHex
    el.style.color = it.hex
    el.textContent = `${it.name} ${it.hex}`
    el.title = `contrast: ${contrastRatio(bgHex, it.hex).toFixed(2)}`
    container.appendChild(el)
  }
}

function render(result) {
  state.lastResult = result
  const colors = result.colors || {}
  const bg = colors.background
  const fg = colors.foreground

  setPreview(result.imagePath)
  document.documentElement.style.setProperty('--gen-bg', bg)
  document.documentElement.style.setProperty('--gen-fg', fg)
  if (colors.surface0) document.documentElement.style.setProperty('--gen-surface0', colors.surface0)
  if (colors.surface1) document.documentElement.style.setProperty('--gen-surface1', colors.surface1)

  if (colors.color0) document.documentElement.style.setProperty('--accent0', colors.color0)
  if (colors.color1) document.documentElement.style.setProperty('--accent1', colors.color1)

  const sample = $('sample')
  sample.style.background = bg
  sample.style.color = fg
  sample.querySelector('.sample__text').textContent = `bg ${bg}  fg ${fg}  contrast ${contrastRatio(bg, fg).toFixed(2)}`

  const termA = []
  const termB = []
  for (let i = 0; i < 8; i++) termA.push(colors[`color${i}`])
  for (let i = 8; i < 16; i++) termB.push(colors[`color${i}`])
  renderStrip8x2($('terminal16'), termA, termB)

  const ansiA = ['black', 'red', 'green', 'yellow', 'blue', 'magenta', 'cyan', 'white'].map((k) => colors[k])
  const ansiB = ['bright_black', 'bright_red', 'bright_green', 'bright_yellow', 'bright_blue', 'bright_magenta', 'bright_cyan', 'bright_white'].map((k) => colors[k])
  renderStrip8x2($('ansi16'), ansiA, ansiB)

  const cols16 = []
  for (let i = 0; i < 16; i++) {
    const k = `color${i}`
    if (colors[k]) cols16.push({ name: k, hex: colors[k] })
  }
  renderGrid($('colors16'), cols16, bg)

  const surfaces = []
  if (colors.background) surfaces.push({ name: 'background', hex: colors.background })
  for (let i = 0; i < 6; i++) {
    const k = `surface${i}`
    if (colors[k]) surfaces.push({ name: k, hex: colors[k] })
  }
  for (let i = 0; i < 3; i++) {
    const k = `subsurface${i}`
    if (colors[k]) surfaces.push({ name: k, hex: colors[k] })
  }
  renderSurfaces($('surfaces'), fg, surfaces)

  const all = []
  for (const [k, v] of Object.entries(colors)) {
    if (!v) continue
    if (/^surface\d+$/.test(k) || /^subsurface\d+$/.test(k)) continue
    all.push({ name: k, color: v })
  }

  const order = (name) => {
    if (name === 'background') return [0, 0]
    if (name === 'foreground') return [0, 1]
    if (name === 'cursor') return [0, 2]
    const m = name.match(/^color(\d+)$/)
    if (m) return [1, parseInt(m[1], 10)]
    const ansi = ['black','red','green','yellow','blue','magenta','cyan','white']
    const bright = ['bright_black','bright_red','bright_green','bright_yellow','bright_blue','bright_magenta','bright_cyan','bright_white']
    const i1 = ansi.indexOf(name)
    if (i1 >= 0) return [2, i1]
    const i2 = bright.indexOf(name)
    if (i2 >= 0) return [3, i2]
    return [9, name]
  }

  all.sort((a, b) => {
    const oa = order(a.name)
    const ob = order(b.name)
    if (oa[0] !== ob[0]) return oa[0] - ob[0]
    if (oa[1] < ob[1]) return -1
    if (oa[1] > ob[1]) return 1
    return 0
  })

  const mid = Math.ceil(all.length / 2)
  renderAccentColumn($('accents-left'), bg, all.slice(0, mid))
  renderAccentColumn($('accents-right'), bg, all.slice(mid))

  $('debug').textContent = (result.debug || []).join('\n')
}

async function generate() {
  if (!state.imagePath) return
  const params = paramsFromUI()
  setReadouts()
  $('debug').textContent = 'Generating...'
  const body = JSON.stringify({ imagePath: state.imagePath, params })
  const result = await api('/api/generate', { method: 'POST', headers: { 'content-type': 'application/json' }, body })
  render(result)
}

function scheduleGenerate() {
  if (state.debounce) clearTimeout(state.debounce)
  state.debounce = setTimeout(() => generate().catch((e) => ($('debug').textContent = String(e))), 250)
}

async function useWallpaper() {
  const info = await api('/api/wallpaper')
  state.imagePath = info.path
  $('image-path').textContent = state.imagePath
  scheduleGenerate()
}

async function uploadFile(file) {
  const fd = new FormData()
  fd.append('file', file)
  const info = await api('/api/upload', { method: 'POST', body: fd })
  state.imagePath = info.path
  $('image-path').textContent = state.imagePath
  scheduleGenerate()
}

function setPreview(path) {
  const img = $('preview-img')
  const label = $('preview-label')
  if (!path) {
    img.removeAttribute('src')
    label.textContent = '(no image)'
    return
  }
  img.src = `/api/image?path=${encodeURIComponent(path)}&t=${Date.now()}`
  label.textContent = path.split('/').slice(-1)[0]
}

function init() {
  setReadouts()

  $('use-wallpaper').addEventListener('click', () => useWallpaper().catch((e) => ($('debug').textContent = String(e))))
  $('regen').addEventListener('click', () => generate().catch((e) => ($('debug').textContent = String(e))))
  $('file').addEventListener('change', (e) => {
    const f = e.target.files && e.target.files[0]
    if (f) uploadFile(f).catch((err) => ($('debug').textContent = String(err)))
  })

  const inputs = [
    'light',
    'shading',
    'generation_strategy',
    'subtractive_initial',
    'choose',
    'shuffle',
    'seed',
    'contrast',
    'brightness',
    'saturate',
    'bg_chroma_floor',
    'greyish_chroma_threshold',
  ]

  for (const id of inputs) {
    $(id).addEventListener('input', scheduleGenerate)
    $(id).addEventListener('change', scheduleGenerate)
  }

  // Auto-load current wallpaper on first load.
  useWallpaper().catch((e) => ($('debug').textContent = String(e)))
}

init()
