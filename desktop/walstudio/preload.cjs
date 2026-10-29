// The Studio page's only access to the desktop: choose wallpapers on this machine, and read where
// the app's backend reads and writes. No filesystem, shell or IPC beyond these two calls.
const { contextBridge, ipcRenderer } = require("electron")

contextBridge.exposeInMainWorld("walstudio", {
  chooseWallpapers: () => ipcRenderer.invoke("walstudio:choose-wallpapers"),
  info: () => ipcRenderer.invoke("walstudio:info"),
})
