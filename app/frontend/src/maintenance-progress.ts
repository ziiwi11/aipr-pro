import type { Bootstrap } from "./types";
/** Update progress without replacing editable inputs or depending on button focus. */
export function showMaintenanceProgress(root:ParentNode,progress:NonNullable<Bootstrap["maintenance"]>,running=false) {
 const label=root.querySelector<HTMLElement>("[data-maintenance-status]");
 if(label)label.textContent=`数据维护：${progress.message || "尚未开始"}${progress.busy ? ` · 已处理 ${Number(progress.files||0).toLocaleString("zh-CN")} 个文件` : ""}`;
 root.querySelectorAll<HTMLButtonElement>("[data-maintenance-action]").forEach(button=>{button.disabled=Boolean(progress.busy||running);});
}
