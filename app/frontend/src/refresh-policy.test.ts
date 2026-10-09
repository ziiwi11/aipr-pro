import { describe, it, expect, beforeEach } from 'vitest';
import { mayRefresh } from './refresh-policy';
describe('background refresh preserves editing', () => {
  beforeEach(() => { document.body.innerHTML = ''; });
  it('waits for unsaved form data even when focus leaves the input', () => {
    document.body.innerHTML = '<form data-editing-draft="true"><input value="draft"></form>';
    expect(mayRefresh()).toBe(false);
    document.querySelector('form')!.remove();
    expect(mayRefresh()).toBe(true);
  });
  it('does not rebuild the outreach selection and preview during background collection updates', () => {
    document.body.innerHTML = '<section id="aipr-leishen-workbench"><input type="checkbox" checked></section>';
    expect(mayRefresh()).toBe(false);
    document.body.innerHTML = '';expect(mayRefresh()).toBe(true);
  });
  it('does not replace a focused input', () => {
    document.body.innerHTML = '<input>';
    document.querySelector('input')!.focus();
    expect(mayRefresh()).toBe(false);
    document.querySelector('input')!.blur();
    expect(mayRefresh()).toBe(true);
  });
  it('preserves keyboard focus on buttons and open dialogs during polling', () => {
    document.body.innerHTML = '<button>导出</button>';
    document.querySelector('button')!.focus();
    expect(mayRefresh()).toBe(false);
    document.querySelector('button')!.blur();
    expect(mayRefresh()).toBe(true);
    document.body.innerHTML = '<dialog open>确认</dialog>';
    expect(mayRefresh()).toBe(false);
  });
});
