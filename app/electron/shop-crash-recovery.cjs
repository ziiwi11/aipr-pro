function createShopCrashRecovery(contents, { emit, now = Date.now, maxCrashes = 3, windowMs = 600000 } = {}) {
  let crashes = [];
  return async (details = {}) => {
    emit?.("failed", { description: details.reason });
    if (details.reason === "clean-exit" || contents.isDestroyed()) return false;
    const timestamp = now();
    crashes = crashes.filter((at) => timestamp - at < windowMs);
    crashes.push(timestamp);
    if (crashes.length > maxCrashes) {
      emit?.("recovery-exhausted", { description: "店铺页面连续崩溃，已停止自动恢复" });
      return false;
    }
    const previous = contents.getURL();
    let target = "https://fxg.jinritemai.com/ffa/mshop/homepage/index";
    try {
      const url = new URL(previous);
      if (url.protocol === "https:" && ["fxg.jinritemai.com", "buyin.jinritemai.com"].includes(url.hostname)) target = previous;
    } catch {}
    try {
      // Reuse the same WebContents and persistent session, retaining shop login.
      await contents.loadURL(target);
      emit?.("recovered", { description: "店铺页面已恢复，继续使用原登录态" });
      return true;
    } catch (error) {
      emit?.("recovery-failed", { description: error.message });
      return false;
    }
  };
}
module.exports = { createShopCrashRecovery };
