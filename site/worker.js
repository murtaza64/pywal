// Palette Studio's backend for a browser tab: pywal's Studio (pywal.studio.web) in Pyodide. Images
// live in Pyodide's in-memory filesystem and never leave the tab.
import { loadPyodide } from "https://cdn.jsdelivr.net/pyodide/v314.0.7/full/pyodide.mjs"

const SAMPLES = ["dusk.jpg", "ember.jpg", "moss.jpg", "tide.jpg"]

const ready = (async () => {
  const py = await loadPyodide()
  await py.loadPackage("pillow")
  py.unpackArchive(await (await fetch("/web/engine.zip")).arrayBuffer(), "zip", { extractDir: "/engine" })
  py.runPython("import sys; sys.path.insert(0, '/engine')")
  const studio = py.pyimport("pywal.studio.web").WebStudio("/web")
  // Generated sample wallpapers (site/build.py) so the studio opens on something.
  for (const name of SAMPLES) {
    const bytes = new Uint8Array(await (await fetch(`/samples/${name}`)).arrayBuffer())
    studio.add_image(`sample-${name}`, bytes)
  }
  return { studio }
})()

self.onmessage = async (event) => {
  const msg = event.data
  try {
    const { studio } = await ready
    if (msg.type === "ready") return self.postMessage({ id: msg.id, ok: true })
    if (msg.type === "add") {
      const paths = msg.files.map((f) => studio.add_image(f.name, new Uint8Array(f.bytes)))
      return self.postMessage({ id: msg.id, ok: true, paths })
    }
    if (msg.type === "api") {
      const out = studio.handle(msg.method, msg.url, msg.body ?? null)
      const [status, mime, bytes] = out.toJs()
      out.destroy()
      return self.postMessage({ id: msg.id, ok: true, status, mime, bytes }, [bytes.buffer])
    }
  } catch (err) {
    // Python exceptions carry the traceback; the last line is the useful one.
    const text = String(err?.message ?? err).trim().split("\n").filter(Boolean).at(-1)
    self.postMessage({ id: msg.id, ok: false, error: text })
  }
}
