import {describe,it,expect,vi,beforeEach} from 'vitest';
import {confirmDraftNavigation,guardDraftNavigation} from './draft-navigation';
describe('navigation protects actual unsaved form data',()=>{
 beforeEach(()=>{document.body.innerHTML='';});
 it('keeps existing navigation immediate when there is no draft',()=>{
  const leave=vi.fn();guardDraftNavigation(document,leave);expect(leave).toHaveBeenCalledOnce();
 });
 it('keeps draft content and cancels navigation on continue editing',async()=>{
  document.body.innerHTML='<form data-editing-draft="true"><input value="未保存资料"></form>';
  const pending=confirmDraftNavigation();
  expect(document.querySelector('dialog[open]')).not.toBeNull();
  expect(document.activeElement?.textContent).toBe('继续编辑');
  const button=Array.from(document.querySelectorAll('button')).find(x=>x.textContent==='继续编辑')!;button.click();
  expect(await pending).toBe(false);expect(document.querySelector('input')!.value).toBe('未保存资料');
  expect(document.querySelector('dialog')).toBeNull();
 });
 it('requires the explicit discard button, Escape also keeps the draft',async()=>{
  document.body.innerHTML='<form data-editing-draft="true"><textarea>原文</textarea></form>';
  const cancel=confirmDraftNavigation();document.querySelector('dialog')!.dispatchEvent(new Event('cancel',{cancelable:true}));expect(await cancel).toBe(false);
  const discard=confirmDraftNavigation();Array.from(document.querySelectorAll('button')).find(x=>x.textContent==='放弃修改并离开')!.click();expect(await discard).toBe(true);
  expect(document.querySelector('textarea')!.value).toBe('原文');
 });
});
