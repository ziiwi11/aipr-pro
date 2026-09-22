const test = require("node:test");
const assert = require("node:assert/strict");

const { mergeRuntimeCollectionStrategy } = require("./collection-strategy-runtime.cjs");

test("运行策略默认启用逐达人流水线和严格明文去重", () => {
  const result = mergeRuntimeCollectionStrategy({
    base: { targetCount: 1000, excludeContacts: ["new-contact"] },
    existing: { excludeContacts: ["old-contact"] },
  });

  assert.equal(result.realtimeCreatorFlow, true);
  assert.equal(result.contactDedupMode, "strict-any-plaintext-value");
  assert.deepEqual(result.excludeContacts, ["old-contact", "new-contact"]);
});

test("用户确认的非关键词结构化发现模式不会被界面默认关键词覆盖", () => {
  const result = mergeRuntimeCollectionStrategy({
    base: { keywords: ["界面默认词"], sourceDiscoveryMode: "keyword_search" },
    existing: { keywords: [], sourceDiscoveryMode: "structured_browse", sourceBrowseProfileId: "video-v1" },
  });

  assert.equal(result.sourceDiscoveryMode, "structured_browse");
  assert.deepEqual(result.keywords, []);
  assert.equal(result.sourceBrowseProfileId, "video-v1");
});
