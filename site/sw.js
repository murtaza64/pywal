// Answers the Studio page's /api requests (fetches, <img> and CSS images alike) by asking the page,
// whose Pyodide worker runs the Studio backend. Nothing goes to the network.
self.addEventListener("install", () => self.skipWaiting())
self.addEventListener("activate", (event) => event.waitUntil(self.clients.claim()))

self.addEventListener("fetch", (event) => {
  const url = new URL(event.request.url)
  if (url.origin !== self.location.origin || !url.pathname.startsWith("/api/")) return
  event.respondWith(forward(event, url))
})

async function forward(event, url) {
  const client = (await self.clients.get(event.clientId || event.resultingClientId)) ?? (await self.clients.matchAll({ type: "window" }))[0]
  if (!client) return new Response(JSON.stringify({ error: "no studio page" }), { status: 503, headers: { "Content-Type": "application/json" } })
  const body = event.request.method === "POST" ? await event.request.text() : null
  const channel = new MessageChannel()
  const reply = new Promise((resolve) => (channel.port1.onmessage = (m) => resolve(m.data)))
  client.postMessage({ type: "api", method: event.request.method, url: url.pathname + url.search, body }, [channel.port2])
  const r = await reply
  return new Response(r.bytes, { status: r.status, headers: { "Content-Type": r.mime, "Cache-Control": "no-store" } })
}
