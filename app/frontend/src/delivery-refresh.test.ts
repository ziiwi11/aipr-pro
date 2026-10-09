import {describe,it,expect} from "vitest";
import {replaceDeliverySection} from "./delivery-refresh";
describe("delivery completion preserves other work",()=>{
  it("shows new artifacts while keeping outreach selection, preview and unsaved input",()=>{
    const root=document.createElement("div");document.body.replaceChildren(root);
    root.innerHTML='<form data-editing-draft="true"><input value="unsaved"></form><section id="aipr-leishen-workbench"><input type="checkbox" checked><p>preview</p></section><div class="delivery-center-page">old</div>';
    const input=root.querySelector<HTMLInputElement>("form input")!;input.focus();
    const workbench=root.querySelector("#aipr-leishen-workbench");
    expect(replaceDeliverySection(root,()=>{const s=document.createElement("div");s.className="delivery-center-page";s.textContent="new export · requires validation";return s;})).toBe(true);
    expect(root.textContent).toContain("new export");expect(root.textContent).not.toContain("old");
    expect(root.querySelector("#aipr-leishen-workbench")).toBe(workbench);
    expect(root.querySelector<HTMLInputElement>('input[type=checkbox]')!.checked).toBe(true);
    expect(document.activeElement).toBe(input);expect(input.value).toBe("unsaved");
  });
  it("does not navigate or destroy another page when an export finishes after navigation",()=>{
    const root=document.createElement("div");root.innerHTML='<form><input value="editing another page"></form>';
    const form=root.firstChild;let rendered=false;
    expect(replaceDeliverySection(root,()=>{rendered=true;return document.createElement("div");})).toBe(false);
    expect(rendered).toBe(false);expect(root.firstChild).toBe(form);
  });
});
