import { it, expect, vi } from 'vitest';
it('shows the latest saved step and elapsed time without calling an active task stopped', async () => {
  // @ts-expect-error standalone JavaScript extension
  const { flowProgress, renderFlow } = await import('./public/aipr-realtime-flow.js');
  const snapshot = { workerRunning: true, updatedAt: '2026-10-06T00:00:00+08:00', records: [
    { state: 'contact_revealing', updated_at: '2026-10-05T23:59:00+08:00' },
    { state: 'listed', updated_at: '2026-10-06T00:00:00+08:00' },
    { state: 'evidence_reviewing', reason: 'model uncertain', updated_at: '2026-10-05T23:50:00+08:00' },
  ] };
  const text = flowProgress(snapshot, Date.parse('2026-10-06T00:02:10+08:00'));
  expect(text).toContain('最近一步：正式入库');
  expect(text).toContain('2 分 10 秒前');
  expect(text).toContain('待复核 1 人');
  expect(text).toContain('等待新结果');
  expect(flowProgress({ ...snapshot, workerRunning: false })).toContain('采集已停止');
  renderFlow(snapshot);
  expect(document.querySelector('[role="status"]')?.textContent).toContain('任务运行中');
  expect(document.querySelector('.aipr-flow-title i')?.className).toBe('running');
});
it('historical plaintext counts do not overwrite the formal contact badge', async () => {
  vi.useFakeTimers();
  document.body.innerHTML = '<button>联系方式 <span>200</span></button>';
  // @ts-expect-error standalone JavaScript extension
  const { renderFlow } = await import('./public/aipr-realtime-flow.js');
  renderFlow({ available: true, workerRunning: false, metrics: { plaintext: 275, listed: 200, contactRevealing: 1 } });
  expect(document.querySelector('button span')!.textContent).toBe('200');
  expect(document.querySelector('.aipr-flow-metric.valid strong')!.textContent).toBe('275');
  expect(document.querySelector('.aipr-flow-metric.formal strong')!.textContent).toBe('200');
  expect(document.querySelector('.aipr-flow-title i')!.className).toBe('');
  vi.clearAllTimers(); vi.useRealTimers();
});
it('completed collection remains completed while the software checks login', async () => {
  // @ts-expect-error standalone JavaScript extension
  const { flowProgress, renderFlow } = await import('./public/aipr-realtime-flow.js');
  const snapshot = { workerRunning: false, taskStatus: 'completed', metrics: { listed: 500 } };
  expect(flowProgress(snapshot)).toContain('采集已完成');
  renderFlow(snapshot);
  expect(document.querySelector('[role="status"]')?.textContent).toContain('交付文件已保存');
  expect(document.querySelector('.aipr-flow-title i')?.className).toBe('');
  expect(flowProgress({ ...snapshot, workerRunning: true })).toContain('任务运行中');
});
