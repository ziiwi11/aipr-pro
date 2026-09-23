# 参照 InfluenceX 的三项迭代

参照项目：[oratis/influencex](https://github.com/oratis/influencex)（MIT，开源 KOL 营销平台）

---

## 一、任务队列（job_queue.py）

**移植自**：`server/job-queue.js`

### 解决什么问题

风控实测数据：
- 连续揭示约 **44 次**后触发软限流（`请求过于频繁` / `稍后再试`）
- 约 **4 分钟**后自动恢复

**没有队列时**：限流 → 直接失败 → 需人工重跑
**有了队列后**：限流 → 指数退避重试 → 自动恢复

### 核心设计

```python
RATE_LIMIT_BACKOFF_MS = 240_000   # 4 分钟，匹配实测恢复窗口

base = rate_limit_backoff_ms if is_rate_limit_error(exc) else base_backoff_ms
backoff_ms = base * (2 ** (attempts - 1)) + random.randint(0, 250)
```

**关键特性：**
- 风控错误使用更长退避基数（240s vs 默认 1s）
- 指数增长 + 抖动（避免惊群）
- 并发控制、暂停/恢复、事件流
- 达到 `max_retries` 后标记失败，不阻塞后续任务

### 用法

```python
from job_queue import create_queue

q = create_queue(concurrency=1)
q.register("reveal-contact", handler)
for uid in uids:
    q.push("reveal-contact", {"uid": uid}, max_retries=3)
stats = q.run_until_drained()
```

### 测试

```bash
python3 -m unittest test_job_queue -v   # 22 个用例
```

---

## 二、ROI 转化看板（roi_dashboard.py）

**移植自**：`server/roi-dashboard.js`

### 核心洞察

InfluenceX 的漏斗是**包含式**的：

> Each stage "contains" the next: a replied contact also counts toward opened,
> delivered, and sent. This lets the UI draw a **monotonic-decreasing funnel**
> instead of a bar chart with awkward gaps.

### 我们的漏斗

```
候选达人 → 已验证 → 预接触合格 → 已揭示联系方式 → 已交付
```

**每个阶段包含下一个**，保证单调递减。

### 输出示例（真实数据）

```
【转化漏斗】
  候选达人          57
  已验证            57   100.0%
  预接触合格        57   100.0%
  已揭示联系方式     57   100.0%
  已交付             0   0.0%
  端到端转化    0.0%

【联系方式】
  有联系方式        57   100.0%
  手机              41
  微信              16

【等级分布】
  LV1               49
  LV2                8

【风控状态】
  触发限流           5

【速率】
  耗时          51.0 分钟
  每分钟揭示    1.12
```

### 用法

```bash
python3 roi_dashboard.py --input "候选人.json" --name "任务名" --elapsed-minutes 51
```

### 测试

```bash
python3 -m unittest test_roi_dashboard -v   # 21 个用例
```

---

## 三、外联回执闭环（outreach_receipts.py）

### 解决什么问题

外联发出后没有闭环 —— 不知道谁发送成功、谁回复了。

### 状态机

```
requested → queued → sent → replied
                  ↘ failed
                  ↘ bounced
```

**合法流转受白名单约束：**
- `requested` → 只能到 `queued` / `failed`
- `sent` → 只能到 `replied` / `bounced` / `failed`
- `replied` → 终态，不可再变
- `failed` / `bounced` → 允许回到 `queued` 重试

**非法跳转（如 `requested` → `sent`）会抛 `TransitionError`。**

### 设计约束

与 `creator_delivery_contract` 的 guardrails 一致：
- **只记录状态，不主动发送**
- 追加式存储（JSONL），便于审计与回放
- 线程安全

### 用法

```python
from outreach_receipts import ReceiptLedger

ledger = ReceiptLedger("receipts.jsonl")
ledger.record("task:uid1", "sent", channel="wechat")
ledger.record("task:uid1", "replied", note="已回复报价")

summary = ledger.summary()
# {'total_events': 1, 'by_state': {...}, 'rates': {'send_rate': '100.0', 'reply_rate': '100.0'}}

# 合并到交付行
from outreach_receipts import merge_receipts_into_rows
rows = merge_receipts_into_rows(rows, ledger, task_id="task")
# 增加字段：外联状态 / 外联渠道 / 外联时间 / 外联备注
```

### 测试

```bash
python3 -m unittest test_outreach_receipts -v   # 25 个用例
```

---

## 四、未采纳的部分

InfluenceX 还有一些模块，当前**未移植**：

| 模块 | 原因 |
|---|---|
| `rbac.js` | 我们是单用户桌面应用 |
| `email-*.js` | 我们的触达走机器人队列，不是邮件 |
| `migrations.js` | 我们用 JSON 文件，暂无 DB |
| `redis-*.js` | 单进程不需要 |
| `openapi.js` | 暂无对外 API |
| `sentry.js` / `otel.js` | 暂无监控需求 |

**如果将来要上多用户或云端部署，这些值得再看。**

---

## 五、回归

```bash
cd app/backend
python3 -m unittest discover -p "test_*.py"
# Ran 359 tests — OK
```

**291（原有）+ 22（队列）+ 21（ROI）+ 25（回执）= 359**
