const BACKGROUND_BOUNDS = Object.freeze({ x: 0, y: 0, width: 1280, height: 900 });

function setShopViewLayout(view, visible, bounds) {
  if (!view) return;
  // Invisible views still need a viewport for evidence screenshots and responsive content.
  view.setBounds(visible ? bounds : BACKGROUND_BOUNDS);
  view.setVisible(visible);
}
module.exports = { setShopViewLayout, BACKGROUND_BOUNDS };
