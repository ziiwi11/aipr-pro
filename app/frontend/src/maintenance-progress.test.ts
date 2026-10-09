import {it,expect} from "vitest";
import {showMaintenanceProgress} from "./maintenance-progress";
it("updates active maintenance progress without replacing focused inputs, and re-enables only stopped-task actions",()=>{
 document.body.innerHTML='<p data-maintenance-status></p><button data-maintenance-action>备份</button><button data-maintenance-action>恢复</button><input value="未保存备注">';
 const input=document.querySelector("input")!;input.focus();
 showMaintenanceProgress(document,{busy:true,message:"正在备份",files:3500,bytes:100,lastBackup:""});
 expect(document.querySelector("p")?.textContent).toContain("3,500");expect([...document.querySelectorAll("button")].every(b=>b.disabled)).toBe(true);expect(document.activeElement).toBe(input);expect(input.value).toBe("未保存备注");
 showMaintenanceProgress(document,{busy:false,message:"备份完成",files:3500,bytes:100,lastBackup:""},true);expect(document.querySelector("button")?.disabled).toBe(true);
 showMaintenanceProgress(document,{busy:false,message:"备份完成",files:3500,bytes:100,lastBackup:""});expect(document.querySelector("button")?.disabled).toBe(false);
});
