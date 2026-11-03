// Palette Studio in a browser tab: the same page as the desktop studio, with its backend in a Pyodide
// worker. A service worker routes the page's /api requests here; this script relays them.
const status = (text, bad = false) => {
  const el = document.getElementById("draft-status")
  el.textContent = text
  el.dataset.s = bad ? "bad" : "busy"
}

const engine = new Worker("/web/worker.js", { type: "module" })
const pending = new Map()
let nextId = 0
const call = (msg, transfer = []) =>
  new Promise((resolve, reject) => {
    const id = ++nextId
    pending.set(id, { resolve, reject })
    engine.postMessage({ ...msg, id }, transfer)
  })
engine.onmessage = (event) => {
  const job = pending.get(event.data.id)
  pending.delete(event.data.id)
  if (event.data.ok) job.resolve(event.data)
  else job.reject(new Error(event.data.error))
}

window.walweb = {
  add: async (files) => {
    const list = await Promise.all(files.map(async (f) => ({ name: f.name, bytes: await f.arrayBuffer() })))
    return (await call({ type: "add", files: list }, list.map((f) => f.bytes))).paths
  },
}

start().catch((err) => status(`could not start: ${err.message}`, true))

async function start() {
  if (!("serviceWorker" in navigator)) throw new Error("this browser has no service workers (needed to run the studio in a tab)")
  navigator.serviceWorker.addEventListener("message", async (event) => {
    if (event.data?.type !== "api") return
    const reply = await call({ type: "api", method: event.data.method, url: event.data.url, body: event.data.body }).catch((err) => ({
      status: 500,
      mime: "application/json",
      bytes: new TextEncoder().encode(JSON.stringify({ error: err.message })),
    }))
    event.ports[0].postMessage({ status: reply.status, mime: reply.mime, bytes: reply.bytes }, [reply.bytes.buffer])
  })
  status("loading the palette engine (about 15 MB, once)…")
  await navigator.serviceWorker.register("/sw.js")
  await navigator.serviceWorker.ready
  if (!navigator.serviceWorker.controller) {
    await Promise.race([
      new Promise((resolve) => navigator.serviceWorker.addEventListener("controllerchange", resolve, { once: true })),
      new Promise((resolve) => setTimeout(resolve, 3000)),
    ])
  }
  // Without the service worker the page's /api requests would go to the web server; the studio
  // never starts in that state (e.g. after a forced reload, which bypasses service workers).
  if (!navigator.serviceWorker.controller) throw new Error("the studio needs its service worker; reload the page normally")
  guard()
  await call({ type: "ready" })
  await import("/static/studio.js")
}

// Belt and braces: an /api fetch that would leave the tab (no controlling service worker) is refused.
function guard() {
  const send = window.fetch.bind(window)
  window.fetch = (input, init) => {
    const url = new URL(input instanceof Request ? input.url : String(input), location.href)
    if (url.origin === location.origin && url.pathname.startsWith("/api/") && !navigator.serviceWorker.controller)
      return Promise.reject(new Error("studio requests stay in this tab; reload the page normally"))
    return send(input, init)
  }
}
