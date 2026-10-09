/** Background updates must not replace a form while the user is editing it. */
export function mayRefresh(root: ParentNode = document): boolean {
  const focused = document.activeElement;
  return !root.querySelector('dialog[open], [role="dialog"]') && !root.querySelector('#aipr-leishen-workbench') && !root.querySelector('[data-editing-draft="true"]') &&
    !(focused && /^(INPUT|TEXTAREA|SELECT|BUTTON|SUMMARY)$/.test(focused.tagName));
}
