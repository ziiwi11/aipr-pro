function preserveMacWindow(event, window, { platform = process.platform, quitting = false } = {}) {
  if (platform !== 'darwin' || quitting) return false;
  event.preventDefault();
  window.hide();
  return true;
}
function activateWindow(window, createWindow) {
  if (!window || window.isDestroyed()) return createWindow();
  window.show();
  window.focus();
  return window;
}
module.exports = { preserveMacWindow, activateWindow };
