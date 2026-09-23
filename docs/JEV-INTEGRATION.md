# JEV 内容复核集成

AIPR Pro 交付物中的 `Jev内容复核` 字段说明。

---

## 一、这是什么

**JEV 是一个独立的「第二意见」审核服务**，对达人的内容匹配度做补充复核。

**关键约束（设计原则）：**

| 约束 | 实现 |
|---|---|
| **只读** | `advisory_only: true` |
| **不影响准入** | `admission_changed: false` |
| **不自动触达** | `auto_send_allowed: false` |
| **失败不阻断** | 服务不可用时降级为 `uncertain`，保留原审核结果 |

**它不会改变任何达人的入库、淘汰或消息发送决策。**

---

## 二、架构

```
AIPR Pro (creator_jev.py)
  ↓ 组装 payload（仅内容字段 + 项目规则）
jev_local_client.py
  ↓ HTTP POST（带 token）
本地网关 127.0.0.1:8771/v1/systemone
  ↓
云端模型（backend: jev-cloud）
  ↓ 返回 answers + integration 元数据
advisory 结果
  ↓
creator_delivery_contract.py → 写入交付行
```

**配置目录：`~/.config/jev-integration/`**

| 文件 | 用途 |
|---|---|
| `enabled-apps` | 应用白名单（含 `aipr-pro`）|
| `token` | 云端凭证 |
| `env` | `ENABLED=1` / `KEV_FALLBACK=1` / `CLOUD_TIMEOUT=8` |
| `events.jsonl` | 审计日志 |

---

## 三、字段结构

交付物每行的 `Jev内容复核` 是 JSON 字符串：

```json
{
  "enabled": true,
  "advisory_only": true,
  "needs_review": true,
  "admission_changed": false,
  "auto_send_allowed": false,
  "route": "uncertain",
  "confidence": 0.42,
  "integration": {
    "version": "1.0.1",
    "request_id": "5da7fa88...",
    "backend": "jev-cloud",
    "needs_review": false,
    "abstentions": [],
    "cloud_error": null,
    "elapsed_ms": 1036
  },
  "evidence_sha256": "0d627bbef8e0..."
}
```

### 字段含义

| 字段 | 说明 |
|---|---|
| `enabled` | 是否启用 JEV |
| `route` | 复核结论：`supported` / `review_conflict` / `uncertain` |
| `confidence` | 模型置信度（< 0.55 自动降为 `uncertain`）|
| `needs_review` | 是否建议人工复核 |
| `admission_changed` | **恒为 false**（不影响准入）|
| `auto_send_allowed` | **恒为 false**（不自动发送）|
| `integration.backend` | 实际使用的后端（`jev-cloud` / `local`）|
| `integration.elapsed_ms` | 调用耗时 |
| `evidence_sha256` | 证据哈希（用于缓存去重）|

---

## 四、route 的三种取值

| 取值 | 含义 | 建议动作 |
|---|---|---|
| `supported` | 作品证据支持当前项目内容方向 | 正常推进 |
| `review_conflict` | 作品与项目要求有明确冲突证据 | **人工核对** |
| `uncertain` | 证据不足、规则不清或无法确认 | 默认值，不影响原流程 |

**注意：`uncertain` 是默认与降级值，不代表「不合格」。**

---

## 五、启用与禁用

### 启用

```bash
# 确认 app 在白名单
cat ~/.config/jev-integration/enabled-apps | grep aipr-pro

# 确认开关
cat ~/.config/jev-integration/env   # ENABLED=1
```

### 禁用

```bash
# 方式一：环境变量（单次运行）
JEV_INTEGRATION=0 python3 finalize_creator_delivery.py ...

# 方式二：从白名单移除
# 编辑 ~/.config/jev-integration/enabled-apps，删除 aipr-pro
```

**禁用后 `Jev内容复核` 字段不会写入，其余功能完全不受影响。**

---

## 六、隐私边界

**只有内容字段会发送给 JEV：**

```python
FIELDS = ('profile_text', 'douyin_content_text', 'content_evidence',
          'bio', 'signature', 'recent_titles', 'recent_sample_size',
          'content_evidence_reviewed', 'category')
```

**明确不发送：**

- ❌ 联系方式（手机/微信）
- ❌ 粉丝数
- ❌ 达人昵称 / 抖音号
- ❌ 身份 ID

**这一点有单元测试覆盖**（`test_payload_contains_only_allowed_fields`）。

---

## 七、降级行为

| 场景 | 行为 |
|---|---|
| 服务不可用 | `route: uncertain`，`reason: 辅助复核服务不可用，保留原审核结果` |
| 返回非法 route | `route: uncertain` |
| 置信度 < 0.55 | `route: uncertain` |
| 缺少内容或规则 | `route: uncertain`，`reason: 缺少内容证据或当前项目规则` |

**任何异常都不会中断交付流程。**

---

## 八、审计

**每次调用写入 `~/.config/jev-integration/events.jsonl`：**

```json
{
  "time": 1790148586.75,
  "app": "aipr-pro",
  "version": "1.0.1",
  "request_id": "25fcb73f...",
  "backend": "jev-cloud",
  "needs_review": false,
  "abstentions": [],
  "cloud_error": null,
  "elapsed_ms": 1036
}
```

**查询 aipr-pro 的调用记录：**

```bash
grep '"app": "aipr-pro"' ~/.config/jev-integration/events.jsonl | wc -l
```

---

## 九、测试

```bash
cd app/backend
python3 -m unittest test_creator_jev -v
```

**16 个用例，覆盖：**

- enabled 判定三条路径
- 禁用时不抛错
- 缺输入降级
- 服务失败降级
- 低置信度降级
- advisory 安全标志恒定
- 缓存命中
- **隐私字段不外泄**
