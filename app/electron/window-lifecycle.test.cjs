const test = require('node:test');
const assert = require('node:assert/strict');
const { preserveMacWindow, activateWindow } = require('./window-lifecycle.cjs');
test('Mac red close hides the window and preserves browser sessions', () => {
  let prevented = false, hidden = false;
  assert.equal(preserveMacWindow({ preventDefault: () => { prevented = true; } },
    { hide: () => { hidden = true; } }, { platform: 'darwin' }), true);
  assert.equal(prevented, true); assert.equal(hidden, true);
});
test('explicit quit and Windows retain normal window close behavior', () => {
  const forbidden = () => assert.fail('should not hide');
  assert.equal(preserveMacWindow({ preventDefault: forbidden }, { hide: forbidden }, { platform: 'darwin', quitting: true }), false);
  assert.equal(preserveMacWindow({ preventDefault: forbidden }, { hide: forbidden }, { platform: 'win32' }), false);
});
test('activate restores hidden window or creates a missing window', () => {
  let shown = false, focused = false, created = false;
  activateWindow({ isDestroyed: () => false, show: () => { shown = true; }, focus: () => { focused = true; } }, () => assert.fail('existing window'));
  assert.equal(shown && focused, true);
  activateWindow(null, () => { created = true; }); assert.equal(created, true);
});
