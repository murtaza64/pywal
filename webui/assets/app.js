const $ = (id) => document.getElementById(id)

const val = (id) => {
  const el = $(id)
  return el ? el.value : ''
}

const isChecked = (id) => {
  const el = $(id)
  return !!(el && el.checked)
}

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
  const c = $('contrast')
  const b = $('brightness')
  const s = $('saturate')
  const si = $('subtractive_initial')
  const bl = $('bg_lightness')
  const bc = $('bg_chroma')
  if (c) $('contrast-val').textContent = c.value
  if (b) $('brightness-val').textContent = b.value
  if (s) $('saturate-val').textContent = s.value
  if (si) $('subtractive_initial-val').textContent = si.value
  if (bl) $('bg_lightness-val').textContent = bl.value
  if (bc) $('bg_chroma-val').textContent = bc.value
}

function setSubtractiveVisibility() {
  const wrap = $('subtractive_initial-wrap')
  const gen = $('generation_strategy')
  if (!wrap || !gen) return
  wrap.style.display = gen.value === 'subtractive' ? '' : 'none'
}

function setSeedVisibility() {
  const wrap = $('seed-wrap')
  const choose = $('choose')
  if (!wrap || !choose) return
  wrap.style.display = choose.value === 'random' || choose.value === 'ansi-shuffle' ? '' : 'none'
}

function randomSeedString() {
  if (window.crypto && window.crypto.getRandomValues) {
    try {
      const a = new BigUint64Array(1)
      window.crypto.getRandomValues(a)
      return a[0].toString(10)
    } catch (_) {
      const a = new Uint32Array(2)
      window.crypto.getRandomValues(a)
      return (BigInt(a[0]) << 32n | BigInt(a[1])).toString(10)
    }
  }
  return String(Math.floor(Math.random() * 1e16))
}

function paramsFromUI() {
  const seedRaw = String(val('seed') || '').trim()
  const seed = seedRaw === '' ? null : seedRaw
  return {
    light: isChecked('light'),
    shading: val('shading'),
    bg_strategy: val('bg_strategy'),
    generation_strategy: val('generation_strategy'),
    subtractive_initial: parseInt(val('subtractive_initial') || '16', 10),
    choose: val('choose'),
    seed,
    contrast: parseFloat(val('contrast')),
    brightness: parseFloat(val('brightness')),
    saturate: parseFloat(val('saturate')),
    bg_lightness: parseFloat(val('bg_lightness')),
    bg_chroma: parseFloat(val('bg_chroma')),
  }
}

function applyParamsToUI(params) {
  if (!params) return

  if ('light' in params) {
    const el = $('light')
    if (el) el.checked = !!params.light
  }
  if ('shading' in params && params.shading) {
    const el = $('shading')
    if (el) el.value = params.shading
  }
  if ('bg_strategy' in params && params.bg_strategy) {
    const el = $('bg_strategy')
    if (el) el.value = params.bg_strategy
  }
  if ('generation_strategy' in params && params.generation_strategy) {
    const el = $('generation_strategy')
    if (el) el.value = params.generation_strategy
  }
  if ('subtractive_initial' in params && params.subtractive_initial != null) {
    const el = $('subtractive_initial')
    if (el) el.value = String(params.subtractive_initial)
  }
  if ('choose' in params && params.choose) {
    const el = $('choose')
    if (el) el.value = params.choose
  }
  if ('seed' in params) {
    const el = $('seed')
    if (el) el.value = params.seed == null ? '' : String(params.seed)
  }
  if ('contrast' in params && params.contrast != null) {
    const el = $('contrast')
    if (el) el.value = String(params.contrast)
  }
  if ('brightness' in params && params.brightness != null) {
    const el = $('brightness')
    if (el) el.value = String(params.brightness)
  }
  if ('saturate' in params && params.saturate != null) {
    const el = $('saturate')
    if (el) el.value = String(params.saturate)
  }

  if ('bg_lightness' in params && params.bg_lightness != null) {
    const el = $('bg_lightness')
    if (el) el.value = String(params.bg_lightness)
  }
  if ('bg_chroma' in params && params.bg_chroma != null) {
    const el = $('bg_chroma')
    if (el) el.value = String(params.bg_chroma)
  }

  setReadouts()
  setSubtractiveVisibility()
  setSeedVisibility()
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

function renderMain8(container, items) {
  container.innerHTML = ''
  for (const it of items) {
    const el = document.createElement('div')
    el.className = 'maincell'
    el.style.background = it.hex
    el.title = `${it.name} ${it.hex}`
    container.appendChild(el)
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
    label.title = `contrast ${contrastRatio(it.hex, bgHex).toFixed(2)}`

    el.appendChild(label)
    container.appendChild(el)
  }
}

function renderColorRows(container, bgHex, names) {
  container.innerHTML = ''
  for (const name of names) {
    const hex = state.lastResult?.colors?.[name]
    if (!hex) continue

    const row = document.createElement('div')
    row.className = 'colorrow'
    row.style.color = hex
    row.title = `contrast ${contrastRatio(bgHex, hex).toFixed(2)}  ${hex}`

    const n = document.createElement('div')
    n.className = 'colorname'
    n.textContent = name

    const h = document.createElement('div')
    h.className = 'colorhex'
    h.textContent = hex

    row.appendChild(n)
    row.appendChild(h)
    container.appendChild(row)
  }
}

function render(result) {
  state.lastResult = result
  const colors = result.colors || {}
  const bg = colors.background
  const fg = colors.foreground

  setPreview(result.imagePath, result.displayPath)
  document.documentElement.style.setProperty('--gen-bg', bg)
  document.documentElement.style.setProperty('--gen-fg', fg)
  if (colors.surface0) document.documentElement.style.setProperty('--gen-surface0', colors.surface0)
  if (colors.surface1) document.documentElement.style.setProperty('--gen-surface1', colors.surface1)

  if (colors.color0) document.documentElement.style.setProperty('--accent0', colors.color0)
  if (colors.color1) document.documentElement.style.setProperty('--accent1', colors.color1)

  const sample = $('sample')
  sample.style.background = 'transparent'
  sample.style.color = fg

  // Syntax highlighting palette.
  for (let i = 0; i < 8; i++) {
    const k = `color${i}`
    if (colors[k]) document.documentElement.style.setProperty(`--c${i}`, colors[k])
  }

  const main8 = []
  for (let i = 0; i < 8; i++) {
    const k = `color${i}`
    if (colors[k]) main8.push({ name: k, hex: colors[k] })
  }
  renderMain8($('main8'), main8)

  const surfaces = []
  for (let i = 2; i >= 0; i--) {
    const k = `subsurface${i}`
    if (colors[k]) surfaces.push({ name: k, hex: colors[k] })
  }
  if (colors.background) surfaces.push({ name: 'background', hex: colors.background })
  for (let i = 0; i < 6; i++) {
    const k = `surface${i}`
    if (colors[k]) surfaces.push({ name: k, hex: colors[k] })
  }
  renderSurfaces($('surfaces'), fg, surfaces)

  const leftNames = [
    ...Array.from({ length: 8 }, (_, i) => `color${i}`),
    'black',
    'red',
    'green',
    'yellow',
    'blue',
    'magenta',
    'cyan',
    'white',
  ]
  const rightNames = [
    ...Array.from({ length: 8 }, (_, i) => `color${i + 8}`),
    'bright_black',
    'bright_red',
    'bright_green',
    'bright_yellow',
    'bright_blue',
    'bright_magenta',
    'bright_cyan',
    'bright_white',
  ]
  const bottomNames = ['foreground']
  renderColorRows($('colors-left'), bg, leftNames)
  renderColorRows($('colors-right'), bg, rightNames)
  renderColorRows($('colors-bottom'), bg, bottomNames)

  $('debug').textContent = (result.debug || []).join('\n')
}

async function generate() {
  if (!state.imagePath) return
  const params = paramsFromUI()
  setReadouts()
  $('debug').textContent = 'Generating...'
  const body = JSON.stringify({ imagePath: state.imagePath, params })
  const result = await api('/api/generate', { method: 'POST', headers: { 'content-type': 'application/json' }, body })
  applyParamsToUI(result.params)
  render(result)
}

async function shuffle(mode) {
  if (!state.imagePath) return
  $('debug').textContent = mode === 'all' ? 'SHUFFLE...' : 'shuffle...'
  const body = JSON.stringify({ imagePath: state.imagePath, mode, params: paramsFromUI() })
  const result = await api('/api/shuffle', { method: 'POST', headers: { 'content-type': 'application/json' }, body })
  applyParamsToUI(result.params)
  scheduleGenerate()
}

function scheduleGenerate() {
  if (state.debounce) clearTimeout(state.debounce)
  state.debounce = setTimeout(() => generate().catch((e) => ($('debug').textContent = String(e))), 250)
}

async function useWallpaper() {
  const info = await api('/api/wallpaper')
  state.imagePath = info.path
  if ($('image-path')) $('image-path').textContent = ''
  setPreview(state.imagePath, info.displayPath)
  scheduleGenerate()
}

async function uploadFile(file) {
  const fd = new FormData()
  fd.append('file', file)
  const info = await api('/api/upload', { method: 'POST', body: fd })
  state.imagePath = info.path
  if ($('image-path')) $('image-path').textContent = ''
  setPreview(state.imagePath, info.displayPath)
  scheduleGenerate()
}

async function browse(direction) {
  if (!state.imagePath) return
  const body = JSON.stringify({ path: state.imagePath, direction })
  const info = await api('/api/browse', { method: 'POST', headers: { 'content-type': 'application/json' }, body })
  state.imagePath = info.path
  setPreview(state.imagePath, info.displayPath)
  scheduleGenerate()
}

function setPreview(path, displayPath) {
  const img = $('thumb-img')
  const label = $('thumb-label')
  if (!path) {
    if (img) img.removeAttribute('src')
    if (label) label.textContent = '(no image)'
    document.documentElement.style.setProperty('--wallpaper-url', 'none')
    if (document.body) document.body.style.setProperty('--wallpaper-url', 'none')
    return
  }
  const src = `/api/image?path=${encodeURIComponent(path)}&t=${Date.now()}`
  if (img) img.src = src
  if (label) label.textContent = displayPath || path

  // Background wallpaper effect (blurred + tinted via CSS).
  const cssUrl = `url("${src}")`
  document.documentElement.style.setProperty('--wallpaper-url', cssUrl)
  if (document.body) document.body.style.setProperty('--wallpaper-url', cssUrl)
}

function init() {
  setReadouts()
  setSubtractiveVisibility()
  setSeedVisibility()

  $('use-wallpaper').addEventListener('click', () => useWallpaper().catch((e) => ($('debug').textContent = String(e))))
  $('regen').addEventListener('click', () => generate().catch((e) => ($('debug').textContent = String(e))))
  $('shuffle-post').addEventListener('click', () => shuffle('post').catch((e) => ($('debug').textContent = String(e))))
  $('shuffle-all').addEventListener('click', () => shuffle('all').catch((e) => ($('debug').textContent = String(e))))
  $('seed-randomize').addEventListener('click', () => {
    const el = $('seed')
    if (!el) return
    el.value = randomSeedString()
    setReadouts()
    scheduleGenerate()
  })

  const prev = $('thumb-prev')
  const next = $('thumb-next')
  if (prev) prev.addEventListener('click', () => browse('prev').catch((e) => ($('debug').textContent = String(e))))
  if (next) next.addEventListener('click', () => browse('next').catch((e) => ($('debug').textContent = String(e))))
  $('file').addEventListener('change', (e) => {
    const f = e.target.files && e.target.files[0]
    if (f) uploadFile(f).catch((err) => ($('debug').textContent = String(err)))
  })

  const inputs = [
    'light',
    'shading',
    'bg_strategy',
    'generation_strategy',
    'subtractive_initial',
    'choose',
    'seed',
    'contrast',
    'brightness',
    'saturate',
    'bg_lightness',
    'bg_chroma',
  ]

  for (const id of inputs) {
    $(id).addEventListener('input', scheduleGenerate)
    $(id).addEventListener('change', scheduleGenerate)
  }

  const gen = $('generation_strategy')
  if (gen) {
    gen.addEventListener('input', setSubtractiveVisibility)
    gen.addEventListener('change', setSubtractiveVisibility)
  }

  const choose = $('choose')
  if (choose) {
    choose.addEventListener('input', setSeedVisibility)
    choose.addEventListener('change', setSeedVisibility)
  }

  // Auto-load current wallpaper on first load.
  useWallpaper().catch((e) => ($('debug').textContent = String(e)))
}

init()
