import { describe,it,expect } from "vitest";
import { createExclusiveAction,readableError } from "./exclusive-action";
describe("maintenance interaction",()=>{
 it("holds the selected task identity through pending changes and releases after rejection for retry",async()=>{
   let finish!:()=>void;const selected:string[]=[];const states:boolean[]=[];
   const action=createExclusiveAction(async(id:string)=>{selected.push(id);await new Promise<void>(r=>finish=r);if(id==='old')throw Error('切换失败');},busy=>states.push(busy));
   const first=action('old'),second=action('other');expect(second).toBe(first);expect(states).toEqual([true]);await Promise.resolve();expect(selected).toEqual(['old']);finish();await expect(first).rejects.toThrow('切换失败');expect(states).toEqual([true,false]);
   const retry=action('new');await Promise.resolve();expect(selected).toEqual(['old','new']);finish();await retry;expect(states).toEqual([true,false,true,false]);
 });
 it("coalesces repeated clicks and releases the button after completion",async()=>{
   let finish!:()=>void;let calls=0;const states:boolean[]=[];
   const action=createExclusiveAction(async()=>{calls++;await new Promise<void>(r=>{finish=r;});},x=>states.push(x));
   const first=action(),second=action();expect(first).toBe(second);await Promise.resolve();expect(calls).toBe(1);expect(states).toEqual([true]);finish();await first;expect(states).toEqual([true,false]);
   const next=action();await Promise.resolve();expect(calls).toBe(2);finish();await next;
 });
 it("allows a retry after failure and keeps the actionable error",async()=>{
   let calls=0;const states:boolean[]=[];const action=createExclusiveAction(async()=>{calls++;throw Error("文件无法读取");},x=>states.push(x));
   await expect(action()).rejects.toThrow("文件无法读取");await expect(action()).rejects.toThrow("文件无法读取");expect(calls).toBe(2);expect(states).toEqual([true,false,true,false]);
   expect(readableError("Error invoking remote method 'aipr:validate-delivery': Error: 数据维护正在进行")).toBe("数据维护正在进行");
   expect(readableError("请检查文件是否可读取")).toBe("请检查文件是否可读取");
 });
});
