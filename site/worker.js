// Palette Studio's backend for a browser tab: pywal's Studio (pywal.studio.web) in Pyodide. Images
// live in Pyodide's in-memory filesystem and never leave the tab; saved themes stay in this browser.
import { loadPyodide } from "https://cdn.jsdelivr.net/pyodide/v314.0.7/full/pyodide.mjs"

const SAMPLES = ["dusk.jpg", "ember.jpg", "moss.jpg", "tide.jpg"]

const ready = (async () => {
  const py = await loadPyodide()
  await py.loadPackage("pillow")
  // Site files resolve against this script (<prefix>/web/worker.js), so any prefix works.
  py.unpackArchive(await (await fetch(new URL("engine.zip", self.location))).arrayBuffer(), "zip", { extractDir: "/engine" })
  const kept = await keep(py)
  // pywal reads XDG_CONFIG_HOME at import: saved themes go to ~/.config/wal/colorschemes there.
  py.runPython("import os, sys; os.environ['XDG_CONFIG_HOME'] = '/walstudio-kept/config'; sys.path.insert(0, '/engine')")
  const studio = py.pyimport("pywal.studio.web").WebStudio("/web", kept)
  // Generated sample wallpapers (site/build.py) so the studio opens on something.
  for (const name of SAMPLES) {
    const bytes = new Uint8Array(await (await fetch(new URL(`../samples/${name}`, self.location))).arrayBuffer())
    studio.add_image(`sample-${name}`, bytes, await decode(name, bytes))
  }
  return { studio, py, kept }
})()

// /walstudio-kept (also the IndexedDB name; the origin may host other apps): saved themes, in this browser's IndexedDB (never sent anywhere). Without IndexedDB (some
// private windows) it is in memory and lasts as long as the tab.
async function keep(py) {
  py.FS.mkdirTree("/walstudio-kept")
  try {
    py.FS.mount(py.FS.filesystems.IDBFS, {}, "/walstudio-kept")
    await sync(py, true)
    return true
  } catch {
    return false
  }
}

const sync = (py, load) => new Promise((resolve, reject) => py.FS.syncfs(load, (err) => (err ? reject(err) : resolve())))

// The browser's decode of a lossy image as [width, height, RGBA], or undefined (None in Python). Chromium decodes JPEG with
// libjpeg-turbo, like the desktop's Pillow; Pyodide's Pillow does not (pywal.decoded). PNG decodes
// the same everywhere, so it is left to Pillow.
async function decode(name, bytes) {
  if (/\.png$/i.test(name) || typeof OffscreenCanvas === "undefined") return undefined
  try {
    const bitmap = await createImageBitmap(new Blob([bytes]), { colorSpaceConversion: "none", premultiplyAlpha: "none", imageOrientation: "none" })
    const ctx = new OffscreenCanvas(bitmap.width, bitmap.height).getContext("2d", { colorSpace: "srgb" })
    ctx.drawImage(bitmap, 0, 0)
    const rgba = new Uint8Array(ctx.getImageData(0, 0, bitmap.width, bitmap.height).data.buffer)
    return [bitmap.width, bitmap.height, rgba]
  } catch {
    return undefined
  }
}

self.onmessage = async (event) => {
  const msg = event.data
  try {
    const { studio, py, kept } = await ready
    if (msg.type === "ready") return self.postMessage({ id: msg.id, ok: true })
    if (msg.type === "add") {
      const paths = []
      for (const f of msg.files) {
        const bytes = new Uint8Array(f.bytes)
        paths.push(studio.add_image(f.name, bytes, await decode(f.name, bytes)))
      }
      return self.postMessage({ id: msg.id, ok: true, paths })
    }
    if (msg.type === "api") {
      const out = studio.handle(msg.method, msg.url, msg.body ?? null)
      const [status, mime, bytes] = out.toJs()
      out.destroy()
      if (kept && msg.method === "POST" && msg.url.startsWith("/api/themes/save") && status === 200) await sync(py, false)
      return self.postMessage({ id: msg.id, ok: true, status, mime, bytes }, [bytes.buffer])
    }
  } catch (err) {
    // Python exceptions carry the traceback; the last line is the useful one.
    console.error(err)
    const text = String(err?.message ?? err).trim().split("\n").filter(Boolean).at(-1)
    self.postMessage({ id: msg.id, ok: false, error: text })
  }
}
