import {h} from './store';

export function guardDraftNavigation(root: ParentNode, onLeave:()=>void, onStay:()=>void = ()=>{}):void {
  if(!root.querySelector('[data-editing-draft="true"]')){onLeave();return;}
  void confirmDraftNavigation(root).then(discard=>discard?onLeave():onStay());
}

/** Keep unsaved form contents in place until the user chooses to leave. */
export function confirmDraftNavigation(root: ParentNode = document): Promise<boolean> {
  if(!root.querySelector('[data-editing-draft="true"]')) return Promise.resolve(true);
  return new Promise(resolve => {
    const dialog=h('dialog',{class:'task-wizard','aria-labelledby':'draft-navigation-title'}) as HTMLDialogElement;
    const finish=(discard:boolean)=>{dialog.close();dialog.remove();resolve(discard);};
    const stay=h('button',{type:'button',text:'继续编辑',onclick:()=>finish(false)});
    dialog.append(h('h2',{id:'draft-navigation-title',text:'还有未保存的修改'}),h('p',{text:'离开会丢弃当前填写的修改。已保存的任务和名单不会改变。'}),h('div',{class:'button-row'},[stay,h('button',{type:'button',text:'放弃修改并离开',onclick:()=>finish(true)})]));
    dialog.addEventListener('cancel',event=>{event.preventDefault();finish(false);});
    document.body.append(dialog);dialog.showModal();stay.focus();
  });
}
