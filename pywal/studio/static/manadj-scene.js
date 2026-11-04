// manaDJ preview: the draft's wal-palette/1 mapped exactly as manaDJ maps it (manadj.js, generated from
// manaDJ's walTheme), drawn as a small Perform view: four waveform rows, four decks, the track list.
// Waveforms run manaDJ's additive-rgb shader formula (styles.ts) on synthetic band envelopes.
import { MANADJ_BASE, backdropProposal, walTheme } from "./manadj.js"

const DECKS = ["A", "B", "C", "D"]
const IDENTITY = { A: "#00e5ff", B: "#ff2d95", C: "#ff7a00", D: "#8f4dff" }
const ADDITIVE = [[1.0, 0.1, 0.1], [0.0, 1.0, 0.25], [0.2, 0.45, 1.0]]
const STATUS = { "--success": "#00e676", "--danger": "#ff2d55", "--warning": "#ffcc00", "--orange": "#ff7a00", "--playhead": "#ffffff" }
const TRACKS = [
  ["A", "Nightcity Drive", "Joi Unit", 124, "8A"],
  ["B", "Rocinante Burn", "Belter Choir", 128, "5A"],
  ["C", "Ember Field", "Static Bloom", 126, "8B"],
  ["D", "Tears in Rain", "Off-world", 122, "1A"],
  ["", "Glass Weather", "Kitty Tint", 120, "11A"],
  ["", "Seven to One", "Readability Floor", 132, "4B"],
  ["", "Subtractive", "Palette Engine", 118, "9A"],
]

export const MDJ_DEFAULTS = { decks: "wall", wave: "default", backdrop: "on" }

const hex = (h) => [1, 3, 5].map((i) => parseInt(h.slice(i, i + 2), 16) / 255)
const esc = (s) => String(s).replace(/[&<>"]/g, (m) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[m])

/** Paint `el` (.mdj) for wal-palette `doc`. `opts`: {decks, wave, backdrop}; `blurred(image)` resolves {url, brightest}. */
export function renderManadj(el, doc, image, opts, blurred) {
  const t = doc ? walTheme(doc, MANADJ_BASE) : { ok: false, reason: "no palette for this layer" }
  const vars = { ...MANADJ_BASE, "--accent": "#4a9eff", ...STATUS, ...(t.ok ? t.vars : {}) }
  const decks = t.ok && opts.decks === "wall" ? t.deckProposal : IDENTITY
  for (const [k, v] of Object.entries(vars)) el.style.setProperty(k, v)
  for (const k of DECKS) el.style.setProperty(`--deck-${k.toLowerCase()}`, decks[k])
  for (const seg of el.querySelectorAll(".mdj-seg")) for (const b of seg.children) b.classList.toggle("on", b.dataset.v === opts[seg.dataset.k])
  el.classList.toggle("refused", !t.ok)

  const preset = t.ok ? t.waveformPresets.find((p) => p.id === opts.wave) : null
  const bands = (k) => preset?.perDeck?.[k] ?? preset?.colors ?? ADDITIVE
  const waves = el.querySelector(".mdj-waves")
  if (waves.children.length !== 4) waves.innerHTML = DECKS.map((k) => `<div class="mdj-wave" data-d="${k}"><canvas></canvas><span>${k}</span></div>`).join("")
  for (const row of waves.children) drawWave(row.querySelector("canvas"), bands(row.dataset.d), vars["--void"], DECKS.indexOf(row.dataset.d))

  el.querySelector(".mdj-decks").innerHTML = DECKS.map((k, i) => {
    const [, title, artist, bpm, key] = TRACKS[i]
    return `<div class="mdj-deck" data-d="${k}"><b class="mdj-badge">${k}</b><span class="mdj-title">${esc(title)}</span><span class="mdj-artist">${esc(artist)}</span>`
      + `<span class="mdj-bpm">${bpm}.0</span><span class="mdj-key">${key}</span><span class="mdj-cue">CUE</span><span class="mdj-play">▶</span></div>`
  }).join("")
  el.querySelector(".mdj-tracks").innerHTML = `<tr><th></th><th>key</th><th>bpm</th><th>title</th><th>artist</th></tr>` + TRACKS.map(([d, title, artist, bpm, key]) =>
    `<tr${d ? ` data-d="${d}"` : ""}><td class="mdj-mark"></td><td class="mdj-k">${key}</td><td class="mdj-b">${bpm}</td><td>${esc(title)}</td><td class="mdj-a">${esc(artist)}</td></tr>`).join("")

  const note = el.querySelector(".mdj-note")
  const bd = el.querySelector(".mdj-bd")
  bd.hidden = !t.ok || opts.backdrop !== "on"
  if (!t.ok) { note.textContent = `manaDJ keeps its default theme: ${t.reason}`; return }
  const src = t.deckReport.source
  note.textContent = `decks ${opts.decks === "wall" ? DECKS.map((k) => `${k} ${src[k]}`).join(" · ") + ` · min gap ${Math.round(t.deckReport.minGap)}°` : "identity"}`
  if (bd.hidden) return
  const req = (bd.dataset.req = image)
  blurred(image).then(({ url, brightest }) => {
    if (bd.dataset.req !== req) return
    // The track-list floor (text 7:1, subtext 4.5:1) over the brightest blurred region of this wallpaper.
    const dim = backdropProposal(t.vars, t.waveformPresets, brightest).scopes.library.dim
    bd.querySelector(".mdj-wp").style.backgroundImage = `url("${url}")`
    bd.querySelector(".mdj-dim").style.opacity = dim
    note.textContent += ` · track list dim ${dim.toFixed(2)} (7:1 floor)`
  }).catch(() => { bd.hidden = true })
}

// additive-rgb (styles.ts): c = BG + sum of each band colour where |y| < that band's amplitude, clamped.
function drawWave(cv, cols, bg, seed) {
  const W = cv.clientWidth, H = cv.clientHeight
  if (W < 8 || H < 4) return
  if (cv.width !== W || cv.height !== H) { cv.width = W; cv.height = H }
  const g = cv.getContext("2d"), img = g.createImageData(W, H), BG = hex(bg), mid = H / 2
  const play = Math.round(W * 0.25)
  for (let x = 0; x < W; x++) {
    const t = (x / W) * 12 + seed * 0.37, beat = t % 1
    const amp = [
      0.9 * Math.exp(-beat * 5) * ((t + seed) % 8 < 7 ? 1 : 0.25),
      0.32 + 0.22 * Math.sin(t * 1.7 + seed) ** 2 + 0.08 * Math.sin(x * 0.37 + seed),
      0.14 + 0.32 * Math.exp(-((beat + 0.5) % 1) * 9) + 0.07 * Math.sin(x * 1.3),
    ]
    const shade = x < play ? 0.55 : 1 // played region reads dimmer
    for (let y = 0; y < H; y++) {
      const yA = Math.abs(y - mid) / mid, c = BG.slice()
      for (let k = 0; k < 3; k++) if (yA < amp[k]) for (let j = 0; j < 3; j++) c[j] += cols[k][j] * shade
      const o = (y * W + x) * 4
      img.data[o] = Math.min(1, c[0]) * 255; img.data[o + 1] = Math.min(1, c[1]) * 255; img.data[o + 2] = Math.min(1, c[2]) * 255; img.data[o + 3] = 255
    }
  }
  for (let y = 0; y < H; y++) { const o = (y * W + play) * 4; img.data[o] = img.data[o + 1] = img.data[o + 2] = 255 }
  g.putImageData(img, 0, 0)
}
