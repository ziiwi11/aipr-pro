/** Coalesce passive polling, but never drop a refresh requested after a mutation. */
export function createRefreshController<T>(load:()=>Promise<T>, apply:(value:T)=>void, fail:(error:unknown)=>void) {
  let flight:Promise<void>|null=null;
  let requested=false;
  return (fresh=true):Promise<void>=>{
    if(flight){if(fresh)requested=true;return flight;}
    flight=(async()=>{
      do {
        requested=false;
        try {const value=await load();if(!requested)apply(value);}catch(error){if(!requested)fail(error);}
      }while(requested);
    })().finally(()=>{flight=null;});
    return flight;
  };
}
