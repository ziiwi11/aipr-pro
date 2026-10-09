/** Keep a deliberate maintenance action single-flight before IPC reports busy. */
export function createExclusiveAction<A extends unknown[]>(action:(...args:A)=>Promise<void>, change:(busy:boolean)=>void) {
  let pending:Promise<void>|null=null;
  return (...args:A):Promise<void>=>{
    if(pending)return pending;
    change(true);
    pending=Promise.resolve().then(()=>action(...args)).finally(()=>{pending=null;change(false);});
    return pending;
  };
}

export function readableError(message:string):string {
  return message.replace(/^Error invoking remote method '[^']+':\s*(?:Error:\s*)?/, "");
}
