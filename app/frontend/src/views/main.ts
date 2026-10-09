/**
 * 主视图入口
 *
 * 组装应用外壳（侧边栏 + 工作区）与当前页面。
 * 结构对齐原版，见 docs/ORIGINAL-UI-SPEC.md。
 */

import type { Bootstrap } from "../types";
import { h, mount } from "../store";
import { renderShell, setCurrentPage, getCurrentPage, type ShellHandlers } from "./shell";
import { renderPage, type PageHandlers } from "./pages";
import {guardDraftNavigation} from '../draft-navigation';

/** 任务创建（侧边栏任务切换用） */
export interface TaskHandlers {
  onCreateTask(name: string, targetCount: number, strategy?: import("../types").CollectionStrategy): void | Promise<void>;
}

export type ViewHandlers = ShellHandlers & PageHandlers & TaskHandlers;

export function renderBootstrap(
  root: HTMLElement,
  state: Bootstrap,
  handlers: ViewHandlers,
): void {
  // 局部重渲染（表格分页/搜索、策略编辑态切换），不触发整页刷新
  const rerender = (): void => renderBootstrap(root, state, handlers);

  const pageBody = renderPage(getCurrentPage(), state, handlers, rerender);

  renderShell(root, state, {
    onNavigate: (pageId) => {
      if(pageId===getCurrentPage())return;
      guardDraftNavigation(root,()=>{
        setCurrentPage(pageId);
        rerender();
        handlers.onNavigate(pageId);
      });
    },
    onSelectTask: taskId => {
      guardDraftNavigation(root,()=>{handlers.onSelectTask(taskId);},()=>{
        const selector=root.querySelector<HTMLSelectElement>('[aria-label="选择品牌任务"]');
        if(selector)selector.value=state.task.id;
      });
    },
    onCreateTask: handlers.onCreateTask,
    onReadBrief: handlers.onReadBrief,
    onUnderstandBrief: handlers.onUnderstandBrief,
    onRefresh: () => guardDraftNavigation(root,handlers.onRefresh),
    onProbeLogin: handlers.onProbeLogin,
  }, pageBody);
}

export function renderError(root: HTMLElement, message: string): void {
  mount(
    root,
    h("div", { class: "fatal-error" }, [
      h("h1", { text: "启动失败" }),
      h("pre", { text: message }),
      h("p", { text: "请确认通过 Electron 启动，且 Python 运行时已就绪。" }),
    ]),
  );
}

export function renderLoading(root: HTMLElement): void {
  mount(root, h("div", { class: "loading", text: "正在加载…" }));
}
