// wal-palette live stylesheet. Include once in a document:
//   <script src="http://127.0.0.1:4790/palette/live.js" defer></script>
// It links the viewing device's palette.css and swaps it when the palette changes, so --wal-*
// colours follow the theme the way a terminal or editor does: no reload, no regeneration.
;(() => {
  const origin = new URL(document.currentScript?.src ?? "http://127.0.0.1:4790/").origin
  let link = document.querySelector('link[data-wal-palette], link[href$="/palette.css"]')
  if (!link) {
    link = Object.assign(document.createElement("link"), { rel: "stylesheet" })
    document.head.prepend(link)
  }
  link.dataset.walPalette = ""
  const swap = (revision) => {
    // Load the new sheet beside the old one and drop the old one after it applies, so nothing flashes.
    const next = Object.assign(document.createElement("link"), { rel: "stylesheet", href: `${origin}/palette.css?rev=${revision}` })
    next.dataset.walPalette = ""
    next.onload = () => { if (link !== next) link.remove(); link = next; document.documentElement.dataset.walRevision = revision }
    link.after(next)
  }
  if (typeof EventSource !== "function") return void (link.href ||= `${origin}/palette.css`)
  const events = new EventSource(`${origin}/palette/events`)
  events.onmessage = (e) => { if (e.data !== document.documentElement.dataset.walRevision) swap(e.data) }
})()
