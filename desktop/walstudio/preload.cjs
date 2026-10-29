// The Studio page's only access to the desktop: choose wallpapers on this machine, read where the
// app's backend reads and writes, and switch between its private profile and the live theme.
const { contextBridge, ipcRenderer } = require("electron")

contextBridge.exposeInMainWorld("walstudio", {
  chooseWallpapers: () => ipcRenderer.invoke("walstudio:choose-wallpapers"),
  info: () => ipcRenderer.invoke("walstudio:info"),
  setMode: (mode) => ipcRenderer.invoke("walstudio:set-mode", mode),
})
