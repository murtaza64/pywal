// Runs the palette engine off the main thread. The image stays in this tab: it is written to
// Pyodide's in-memory filesystem and never sent anywhere.
import { loadPyodide } from "https://cdn.jsdelivr.net/pyodide/v314.0.7/full/pyodide.mjs"

const ready = (async () => {
  const py = await loadPyodide()
  await py.loadPackage("pillow")
  py.unpackArchive(await (await fetch("engine.zip")).arrayBuffer(), "zip", { extractDir: "/engine" })
  py.runPython("import sys; sys.path.insert(0, '/engine')")
  return { py, engine: py.pyimport("walexport") }
})()

self.onmessage = async (event) => {
  const msg = event.data
  try {
    const { py, engine } = await ready
    if (msg.type === "warm") return self.postMessage({ id: msg.id, ok: true })
    if (msg.type === "generate") {
      const path = `/tmp/walstudio/in/${msg.name.replace(/[^\w.-]/g, "_")}`
      py.FS.mkdirTree("/tmp/walstudio/in")
      py.FS.writeFile(path, new Uint8Array(msg.bytes))
      const result = engine.generate(path, msg.name, JSON.stringify(msg.settings))
      const out = result.toJs({ dict_converter: Object.fromEntries, create_proxies: false })
      result.destroy()
      py.FS.unlink(path)
      return self.postMessage({ id: msg.id, ok: true, ...out })
    }
  } catch (err) {
    // Python exceptions arrive with the traceback in the message; keep its last line for the UI.
    const text = String(err?.message ?? err).trim().split("\n").filter(Boolean).at(-1)
    self.postMessage({ id: msg.id, ok: false, error: text })
  }
}
