// WalStudio: Palette Studio as a desktop app. The app owns one Studio backend on a free loopback port
// and stops it on quit; the renderer is the Studio page, sandboxed, with one bridge call to choose
// wallpapers on this machine. Apply writes only the configured live directory and targets.
const { app, BrowserWindow, dialog, ipcMain, Menu, shell } = require("electron")
const { spawn, execFileSync } = require("node:child_process")
const fs = require("node:fs")
const net = require("node:net")
const path = require("node:path")

app.setName("WalStudio")
if (!app.requestSingleInstanceLock()) app.quit()

const IMAGE = /\.(png|jpe?g|webp|bmp|gif|tiff?)$/i
const data = () => app.getPath("userData")
const configFile = () => path.join(data(), "config.json")

// Settings: environment overrides, then the saved config, then app-owned defaults. The default live
// directory is the app's own profile, so a fresh install never writes the user's real theme.
const settings = () => {
  const saved = readJson(configFile()) ?? {}
  return {
    // A bundle records the pywal checkout it was built from; a source run uses the checkout it sits in.
    pywal: process.env.WALSTUDIO_PYWAL ?? saved.pywal ?? readJson(path.join(__dirname, "package.json"))?.walstudio?.pywal ?? path.resolve(__dirname, "..", ".."),
    wallpapers: process.env.WALSTUDIO_WALLPAPERS ?? saved.wallpapers ?? path.join(app.getPath("home"), "wallpapers"),
    liveDir: process.env.WALSTUDIO_LIVE_DIR ?? saved.liveDir ?? path.join(data(), "profile", "live"),
    targets: process.env.WALSTUDIO_TARGETS ?? saved.targets ?? "files,es-desktop",
    receipt: process.env.WALSTUDIO_ES_RECEIPT ?? saved.receipt,
  }
}

const backend = { proc: undefined, port: 0, log: undefined }
let win

app.whenReady().then(async () => {
  Menu.setApplicationMenu(menu())
  ipcMain.handle("walstudio:choose-wallpapers", (event) => {
    if (event.senderFrame?.url && !event.senderFrame.url.startsWith(origin())) return undefined
    return chooseWallpapers()
  })
  ipcMain.handle("walstudio:info", (event) => {
    if (event.senderFrame?.url && !event.senderFrame.url.startsWith(origin())) return undefined
    const s = settings()
    return { wallpapers: s.wallpapers, liveDir: s.liveDir, targets: s.targets.split(","), log: backend.log }
  })
  await start()
  open()
})

app.on("second-instance", () => win?.focus())
app.on("window-all-closed", () => app.quit())
app.on("before-quit", () => stop())
process.on("exit", () => stop())

function open() {
  win = new BrowserWindow({
    width: 1440,
    height: 900,
    title: "WalStudio",
    backgroundColor: "#0c0c0d",
    webPreferences: { preload: path.join(__dirname, "preload.cjs"), contextIsolation: true, sandbox: true, nodeIntegration: false },
  })
  // The window shows the app's own backend only; anything else opens nowhere.
  win.webContents.on("will-navigate", (event, url) => { if (!url.startsWith(origin())) event.preventDefault() })
  win.webContents.setWindowOpenHandler(() => ({ action: "deny" }))
  win.loadURL(`${origin()}/`)
}

const origin = () => `http://127.0.0.1:${backend.port}`

async function start() {
  const s = settings()
  fs.mkdirSync(s.liveDir, { recursive: true })
  fs.mkdirSync(path.join(data(), "logs"), { recursive: true })
  backend.port = await freePort()
  backend.log = path.join(data(), "logs", "studio.log")
  const out = fs.openSync(backend.log, "a")
  const python = pythonFor(s.pywal)
  const args = ["-m", "pywal.studio", "--port", String(backend.port), "--allow-apply", "--targets", s.targets,
    "--live-dir", s.liveDir, "--wallpapers", s.wallpapers, "--scratch", path.join(data(), "scratch"), "--backups", path.join(data(), "backups")]
  backend.proc = spawn(python, args, {
    cwd: s.pywal,
    env: { ...process.env, PATH: `/opt/homebrew/bin:/usr/local/bin:${process.env.PATH ?? "/usr/bin:/bin"}`, ...(s.receipt ? { PYWAL_STUDIO_ES_RECEIPT: s.receipt } : {}) },
    stdio: ["ignore", out, out],
  })
  backend.proc.on("exit", (code) => { if (backend.proc && code !== null && code !== 0) dialog.showErrorBox("WalStudio", `The Studio backend stopped (exit ${code}). Log: ${backend.log}`) })
  for (const delay of [100, 200, 400, 800, 1600, 3200, 6400]) {
    if (await up()) return
    await new Promise((resolve) => setTimeout(resolve, delay))
  }
  dialog.showErrorBox("WalStudio", `The Studio backend did not start. Log: ${backend.log}`)
}

function stop() {
  const proc = backend.proc
  backend.proc = undefined
  if (!proc || proc.exitCode !== null) return
  proc.kill("SIGTERM")
  setTimeout(() => proc.exitCode === null && proc.kill("SIGKILL"), 3000).unref()
}

async function chooseWallpapers() {
  // WALSTUDIO_TEST_PICK answers the picker for automated checks (a macOS dialog cannot be driven).
  const result = process.env.WALSTUDIO_TEST_PICK ? { canceled: false, filePaths: [process.env.WALSTUDIO_TEST_PICK] } : await dialog.showOpenDialog(win, {
    title: "Choose wallpapers",
    message: "Choose a folder of wallpapers, or one image",
    properties: ["openDirectory", "openFile"],
    filters: [{ name: "Images", extensions: ["png", "jpg", "jpeg", "webp", "bmp", "gif", "tif", "tiff"] }],
  })
  const chosen = result.filePaths[0]
  if (result.canceled || !chosen) return undefined
  const stat = fs.statSync(chosen)
  if (!stat.isDirectory() && !IMAGE.test(chosen)) return { error: "Not an image" }
  const folder = stat.isDirectory() ? chosen : path.dirname(chosen)
  const file = stat.isDirectory() ? undefined : chosen
  writeJson(configFile(), { ...(readJson(configFile()) ?? {}), wallpapers: folder })
  // The backend serves images only from its wallpaper folder, so a new folder means a new backend.
  stop()
  await start()
  win.loadURL(`${origin()}/${file ? `#pick=${encodeURIComponent(file)}` : ""}`)
  return { folder, file }
}

function menu() {
  return Menu.buildFromTemplate([
    { role: "appMenu" },
    { label: "File", submenu: [
      { label: "Choose Wallpapers…", accelerator: "CmdOrCtrl+O", click: () => chooseWallpapers() },
      { label: "Show Studio Log", click: () => backend.log && shell.showItemInFolder(backend.log) },
      { type: "separator" },
      { role: "close" },
    ] },
    { role: "editMenu" },
    { role: "viewMenu" },
    { role: "windowMenu" },
  ])
}

function pythonFor(pywal) {
  if (process.env.WALSTUDIO_PYTHON) return process.env.WALSTUDIO_PYTHON
  const uv = ["/opt/homebrew/bin/uv", path.join(app.getPath("home"), ".local/bin/uv"), "/usr/local/bin/uv"].find((p) => fs.existsSync(p))
  if (!uv) throw new Error("WalStudio needs uv (https://docs.astral.sh/uv/) or WALSTUDIO_PYTHON")
  return execFileSync(uv, ["run", "python", "-c", "import sys; print(sys.executable)"], { cwd: pywal }).toString().trim()
}

function freePort() {
  return new Promise((resolve, reject) => {
    const server = net.createServer()
    server.on("error", reject)
    server.listen(0, "127.0.0.1", () => {
      const port = server.address().port
      server.close(() => resolve(port))
    })
  })
}

async function up() {
  try {
    return (await fetch(`${origin()}/api/state`)).ok
  } catch {
    return false
  }
}

function readJson(file) {
  try {
    return JSON.parse(fs.readFileSync(file, "utf8"))
  } catch {
    return undefined
  }
}

function writeJson(file, value) {
  fs.mkdirSync(path.dirname(file), { recursive: true })
  fs.writeFileSync(file, JSON.stringify(value, null, 2))
}
