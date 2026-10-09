import {describe,it,expect} from 'vitest';
import {createRefreshController} from './refresh-controller';
describe('bootstrap refresh',()=>{
 it('coalesces passive reads and does not show a stale response after a save',async()=>{
   const pending:Array<(n:number)=>void>=[];const values:number[]=[];
   const refresh=createRefreshController(()=>new Promise<number>(resolve=>pending.push(resolve)),v=>values.push(v),()=>{});
   const first=refresh(false);expect(refresh(false)).toBe(first);expect(pending).toHaveLength(1);
   const afterSave=refresh();pending.shift()!(1);await Promise.resolve();expect(values).toEqual([]);expect(pending).toHaveLength(1);
   pending.shift()!(2);await afterSave;expect(values).toEqual([2]);
 });
 it('recovers after a failed read',async()=>{
   let count=0;const errors:unknown[]=[];const values:number[]=[];
   const refresh=createRefreshController(async()=>{if(++count===1)throw new Error('read');return 2;},v=>values.push(v),e=>errors.push(e));
   await refresh();await refresh();expect(errors).toHaveLength(1);expect(values).toEqual([2]);
 });
});
