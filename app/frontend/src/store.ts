/**
 * 轻量状态容器
 *
 * 不引入框架：主 bundle 已是 React 产物，但源码缺失；
 * 重写版本用最小实现，避免依赖树膨胀，也便于与增量脚本共存。
 */

export type Listener<T> = (state: T) => void;

export class Store<T extends object> {
  private state: T;
  private listeners = new Set<Listener<T>>();

  constructor(initial: T) {
    this.state = initial;
  }

  get(): T {
    return this.state;
  }

  set(patch: Partial<T> | ((prev: T) => Partial<T>)): void {
    const next = typeof patch === "function" ? patch(this.state) : patch;
    this.state = { ...this.state, ...next };
    this.emit();
  }

  subscribe(listener: Listener<T>): () => void {
    this.listeners.add(listener);
    // 首次同步调用也要包 try/catch：订阅者抛错不应中断 subscribe 本身，
    // 否则后续订阅者拿不到初始状态（与 emit 的行为保持一致）。
    try {
      listener(this.state);
    } catch (err) {
      console.error("[store] listener error", err);
    }
    return () => this.listeners.delete(listener);
  }

  private emit(): void {
    for (const listener of this.listeners) {
      try {
        listener(this.state);
      } catch (err) {
        console.error("[store] listener error", err);
      }
    }
  }
}

/** 创建元素的小工具 */
export function h<K extends keyof HTMLElementTagNameMap>(
  tag: K,
  attrs: Record<string, unknown> = {},
  children: (Node | string)[] = [],
): HTMLElementTagNameMap[K] {
  const el = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs)) {
    if (value === null || value === undefined || value === false) continue;
    if (key === "class") el.className = String(value);
    else if (key === "text") el.textContent = String(value);
    else if (key === "html") el.innerHTML = String(value);
    else if (key.startsWith("on") && typeof value === "function") {
      el.addEventListener(key.slice(2).toLowerCase(), value as EventListener);
    } else if (key === "dataset" && typeof value === "object") {
      Object.assign(el.dataset, value as Record<string, string>);
    } else {
      el.setAttribute(key, String(value));
    }
  }
  for (const child of children) {
    el.append(typeof child === "string" ? document.createTextNode(child) : child);
  }
  return el;
}

/** 清空并重填容器 */
export function mount(container: HTMLElement, ...nodes: Node[]): void {
  container.replaceChildren(...nodes);
}

/** 数字格式化（千分位） */
export function fmtNum(value: unknown): string {
  const n = Number(value);
  if (!Number.isFinite(n)) return "0";
  return n.toLocaleString("zh-CN");
}

/** 时间格式化 */
export function fmtTime(value: unknown): string {
  if (!value) return "-";
  const d = new Date(String(value));
  if (Number.isNaN(d.getTime())) return String(value);
  return d.toLocaleString("zh-CN", { hour12: false });
}
