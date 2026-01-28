const $ = (id) => document.getElementById(id)

function clamp(x, lo, hi) {
  if (x < lo) return lo
  if (x > hi) return hi
  return x
}

function lerp(a, b, t) {
  return a + (b - a) * t
}

function srgbToLinear(u) {
  return u <= 0.04045 ? u / 12.92 : Math.pow((u + 0.055) / 1.055, 2.4)
}

function linearToSrgb(u) {
  return u <= 0.0031308 ? 12.92 * u : 1.055 * Math.pow(u, 1 / 2.4) - 0.055
}

function inGamut01(rgb) {
  return rgb[0] >= 0 && rgb[0] <= 1 && rgb[1] >= 0 && rgb[1] <= 1 && rgb[2] >= 0 && rgb[2] <= 1
}

function oklabToLinearSrgb(lab) {
  const L = lab[0], a = lab[1], b = lab[2]
  const l_ = L + 0.3963377774 * a + 0.2158037573 * b
  const m_ = L - 0.1055613458 * a - 0.0638541728 * b
  const s_ = L - 0.0894841775 * a - 1.2914855480 * b

  const l = l_ * l_ * l_
  const m = m_ * m_ * m_
  const s = s_ * s_ * s_

  const lr = 4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s
  const lg = -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s
  const lb = -0.0041960863 * l - 0.7034186147 * m + 1.7076147010 * s
  return [lr, lg, lb]
}

function linearSrgbToOklab(lrgb) {
  const lr = lrgb[0], lg = lrgb[1], lb = lrgb[2]
  const l = 0.4122214708 * lr + 0.5363325363 * lg + 0.0514459929 * lb
  const m = 0.2119034982 * lr + 0.6806995451 * lg + 0.1073969566 * lb
  const s = 0.0883024619 * lr + 0.2817188376 * lg + 0.6299787005 * lb

  const l_ = Math.cbrt(l)
  const m_ = Math.cbrt(m)
  const s_ = Math.cbrt(s)

  const L = 0.2104542553 * l_ + 0.7936177850 * m_ - 0.0040720468 * s_
  const a = 1.9779984951 * l_ - 2.4285922050 * m_ + 0.4505937099 * s_
  const b = 0.0259040371 * l_ + 0.7827717662 * m_ - 0.8086757660 * s_
  return [L, a, b]
}

function oklchToOklab(lch) {
  const L = lch[0], C = lch[1], h = lch[2]
  return [L, C * Math.cos(h), C * Math.sin(h)]
}

function oklabDistance(a, b) {
  const d0 = a[0] - b[0]
  const d1 = a[1] - b[1]
  const d2 = a[2] - b[2]
  return Math.sqrt(d0 * d0 + d1 * d1 + d2 * d2)
}

function circleDistRad(a, b) {
  const twoPi = 2 * Math.PI
  let d = Math.abs(a - b) % twoPi
  return Math.min(d, twoPi - d)
}

function oklchToSrgb01GamutMapped(lch) {
  const L = lch[0]
  const C = Math.max(0, lch[1])
  const h = lch[2]

  const rgb0 = oklabToLinearSrgb(oklchToOklab([L, C, h])).map(linearToSrgb)
  if (inGamut01(rgb0)) {
    return { rgb: rgb0, C_used: C, clipped: false }
  }

  let lo = 0.0
  let hi = C
  let best = 0.0
  for (let i = 0; i < 30; i++) {
    const mid = (lo + hi) / 2
    const rgb = oklabToLinearSrgb(oklchToOklab([L, mid, h])).map(linearToSrgb)
    if (inGamut01(rgb)) {
      best = mid
      lo = mid
    } else {
      hi = mid
    }
  }
  const rgbBest = oklabToLinearSrgb(oklchToOklab([L, best, h])).map(linearToSrgb)
  return { rgb: rgbBest, C_used: best, clipped: true }
}

function rgb01ToHex(rgb) {
  const r = Math.round(clamp(rgb[0], 0, 1) * 255)
  const g = Math.round(clamp(rgb[1], 0, 1) * 255)
  const b = Math.round(clamp(rgb[2], 0, 1) * 255)
  return `#${r.toString(16).padStart(2, '0')}${g.toString(16).padStart(2, '0')}${b.toString(16).padStart(2, '0')}`
}

function fgForBg(rgb) {
  const lin = rgb.map(srgbToLinear)
  const L = 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]
  return L > 0.45 ? '#111111' : '#f5f5f5'
}

function targetsBase() {
  const hex = {
    red: '#ff0000',
    yellow: '#dec838',
    green: '#00ff00',
    cyan: '#00ffff',
    blue: '#0000ff',
    magenta: '#ff00ff',
  }

  const out = {}
  for (const k of Object.keys(hex)) {
    const h = hex[k]
    const r = parseInt(h.slice(1, 3), 16) / 255
    const g = parseInt(h.slice(3, 5), 16) / 255
    const b = parseInt(h.slice(5, 7), 16) / 255
    const lab = linearSrgbToOklab([srgbToLinear(r), srgbToLinear(g), srgbToLinear(b)])
    // OKLCH hue for the target is derived from this canonical color.
    const hue = Math.atan2(lab[2], lab[1])
    out[k] = { hex: h, lab, hue }
  }
  return out
}

function buildTargetsWithYellowOverride(y_center_deg) {
  const base = targetsBase()
  const h = (y_center_deg * Math.PI) / 180
  const L = 0.92
  const C = 0.20
  const mapped = oklchToSrgb01GamutMapped([L, C, h])
  const lab = linearSrgbToOklab(mapped.rgb.map(srgbToLinear))
  base.yellow = {
    hex: rgb01ToHex(mapped.rgb),
    lab,
    hue: Math.atan2(lab[2], lab[1]),
    override: { L, C, h, C_used: mapped.C_used, clipped: mapped.clipped },
  }
  return base
}

function classify(rgbLab, hueRad, L, C, opts) {
  const { mode, k, y_center_rad, y_width_rad, y_min_L, y_min_C, targets } = opts

  const names = ['red', 'yellow', 'green', 'cyan', 'blue', 'magenta']
  let best = 'red'
  let bestScore = Infinity

  for (const t of names) {
    let score
    if (mode === 'base') {
      score = oklabDistance(rgbLab, targets[t].lab)
    } else {
      const dLab = oklabDistance(rgbLab, targets[t].lab)
      const dHue = circleDistRad(hueRad, targets[t].hue)
      score = dLab + k * dHue
    }

    if (mode === 'huepen+gate' && t === 'yellow') {
      const dZone = circleDistRad(hueRad, y_center_rad)
      if (L < y_min_L || C < y_min_C || dZone > y_width_rad / 2) {
        score = Infinity
      }
    }

    if (score < bestScore) {
      bestScore = score
      best = t
    }
  }

  return best
}

function tag(t) {
  return { red: 'R', yellow: 'Y', green: 'G', cyan: 'C', blue: 'B', magenta: 'M' }[t]
}

function read() {
  const mode = $('mode').value
  const k = parseFloat($('k').value)
  const L = parseFloat($('L').value)
  const h_center = parseFloat($('h_center').value)
  const h_span = parseFloat($('h_span').value)
  const h_step = parseFloat($('h_step').value)
  const c_min = parseFloat($('c_min').value)
  const c_max = parseFloat($('c_max').value)
  const c_step = parseFloat($('c_step').value)
  const y_center = parseFloat($('y_center').value)
  const y_width = parseFloat($('y_width').value)
  const y_min_L = parseFloat($('y_min_L').value)
  const y_min_C = parseFloat($('y_min_C').value)
  const show_zone = $('show_zone').checked
  const show_clip = $('show_clip').checked
  return { mode, k, L, h_center, h_span, h_step, c_min, c_max, c_step, y_center, y_width, y_min_L, y_min_C, show_zone, show_clip }
}

function setReadouts(s) {
  $('k-val').textContent = s.k.toFixed(2)
  $('L-val').textContent = s.L.toFixed(3)
  $('h_center-val').textContent = String(Math.round(s.h_center))
  $('h_span-val').textContent = String(Math.round(s.h_span))
  $('h_step-val').textContent = String(Math.round(s.h_step))
  $('c_min-val').textContent = s.c_min.toFixed(3)
  $('c_max-val').textContent = s.c_max.toFixed(3)
  $('c_step-val').textContent = s.c_step.toFixed(3)
  $('y_center-val').textContent = String(Math.round(s.y_center))
  $('y_width-val').textContent = String(Math.round(s.y_width))
  $('y_min_L-val').textContent = s.y_min_L.toFixed(2)
  $('y_min_C-val').textContent = s.y_min_C.toFixed(3)
}

let raf = null
function schedule() {
  if (raf) cancelAnimationFrame(raf)
  raf = requestAnimationFrame(render)
}

function render() {
  raf = null
  const s = read()
  setReadouts(s)

  const grid = $('grid')
  const stats = $('stats')

  const h_center = ((s.h_center % 360) + 360) % 360
  const h_start = h_center - s.h_span
  const h_end = h_center + s.h_span

  const hues = []
  for (let hd = h_start; hd <= h_end + 1e-9; hd += s.h_step) hues.push(hd)

  const c_min = Math.min(s.c_min, s.c_max)
  const c_max = Math.max(s.c_min, s.c_max)
  const chromas = []
  for (let c = c_min; c <= c_max + 1e-9; c += s.c_step) chromas.push(c)
  chromas.reverse()

  const cols = 1 + hues.length
  const rows = 1 + chromas.length
  grid.style.gridTemplateColumns = `repeat(${cols}, 18px)`
  grid.style.gridTemplateRows = `repeat(${rows}, 18px)`

  const y_center_rad = (s.y_center * Math.PI) / 180
  const y_width_rad = (s.y_width * Math.PI) / 180

  const targets = buildTargetsWithYellowOverride(s.y_center)
  if (targets.yellow.override) {
    const o = targets.yellow.override
    stats.textContent = `yellow target: ${targets.yellow.hex} (OKLCH h=${s.y_center.toFixed(0)} C_used=${o.C_used.toFixed(3)}${o.clipped ? ' clipped' : ''})`
  } else {
    stats.textContent = ''
  }

  const frag = document.createDocumentFragment()
  const seen = new Set()
  let clippedCount = 0
  let yellowCount = 0
  let cellCount = 0

  // Axis header.
  const corner = document.createElement('div')
  corner.className = 'yzcell yzcell--axis'
  corner.textContent = 'h'
  frag.appendChild(corner)
  for (const hd of hues) {
    const el = document.createElement('div')
    el.className = 'yzcell yzcell--axis'
    el.textContent = String(((Math.round(hd) % 360) + 360) % 360)
    frag.appendChild(el)
  }

  for (const c of chromas) {
    const lab = document.createElement('div')
    lab.className = 'yzcell yzcell--axis'
    lab.textContent = c.toFixed(2)
    frag.appendChild(lab)

    for (const hd of hues) {
      const hRad = (((hd % 360) + 360) % 360) * (Math.PI / 180)
      const mapped = oklchToSrgb01GamutMapped([s.L, c, hRad])
      const hex = rgb01ToHex(mapped.rgb)
      const bg = hex
      const fg = fgForBg(mapped.rgb)

      const labColor = linearSrgbToOklab(mapped.rgb.map(srgbToLinear))
      const hueRad = Math.atan2(labColor[2], labColor[1])
      const chosen = classify(labColor, hueRad, s.L, c, {
        mode: s.mode,
        k: s.k,
        y_center_rad,
        y_width_rad,
        y_min_L: s.y_min_L,
        y_min_C: s.y_min_C,
        targets,
      })

      const el = document.createElement('div')
      el.className = 'yzcell'
      el.style.background = bg
      el.style.color = fg
      el.textContent = tag(chosen)

      const dZone = circleDistRad(hueRad, y_center_rad)
      const inZone = dZone <= y_width_rad / 2
      if (s.show_zone && inZone) el.classList.add('yzcell--zone')

      if (mapped.clipped) {
        clippedCount += 1
        if (s.show_clip) el.classList.add('yzcell--clip')
      }

      if (chosen === 'yellow') yellowCount += 1
      cellCount += 1
      seen.add(hex)

      const tip = [
        `hex ${hex}`,
        `req: L=${s.L.toFixed(3)} C=${c.toFixed(3)} h=${(((hd % 360) + 360) % 360).toFixed(1)}deg`,
        `used: C=${mapped.C_used.toFixed(3)}${mapped.clipped ? ' (clipped)' : ''}`,
        `chosen=${chosen}`,
        `zone: center=${s.y_center.toFixed(0)} width=${s.y_width.toFixed(0)} d=${(dZone * 180 / Math.PI).toFixed(1)}deg`,
      ].join('\n')
      el.title = tip

      frag.appendChild(el)
    }
  }

  grid.replaceChildren(frag)
  const extra = `cells=${cellCount} unique_hex=${seen.size} clipped=${clippedCount} chosen_yellow=${yellowCount}`
  stats.textContent = stats.textContent ? `${stats.textContent}  |  ${extra}` : extra
}

function hook() {
  const ids = [
    'mode',
    'k',
    'L',
    'h_center',
    'h_span',
    'h_step',
    'c_min',
    'c_max',
    'c_step',
    'y_center',
    'y_width',
    'y_min_L',
    'y_min_C',
    'show_zone',
    'show_clip',
  ]
  for (const id of ids) {
    const el = $(id)
    if (!el) continue
    el.addEventListener('input', schedule)
    el.addEventListener('change', schedule)
  }
  render()
}

hook()
