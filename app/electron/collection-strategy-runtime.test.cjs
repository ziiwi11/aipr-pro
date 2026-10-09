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


test("恢复任务保留自动补充关键词，避免旧界面覆盖已保存发现模式", () => {
  const result = mergeRuntimeCollectionStrategy({
    base: { keywords: [], sourceDiscoveryMode: "structured_browse", targetCount: 200 },
    existing: { keywords: ["唇部护理", "日常好物", "唇部护理"], sourceDiscoveryMode: "keyword_search", replenishmentRound: 12 },
  });
  assert.equal(result.sourceDiscoveryMode, "keyword_search");
  assert.deepEqual(result.keywords, ["唇部护理", "日常好物"]);
  assert.equal(result.replenishmentRound, 12);
  assert.equal(result.targetCount, 200);
});

test('explicit saved category switch overrides old runtime keywords while retaining cross-batch exclusions',()=>{
 const result=mergeRuntimeCollectionStrategy({base:{sourceDiscoveryMode:'structured_browse',keywords:[],maximumFollowers:0,targetCount:1000},existing:{sourceDiscoveryMode:'keyword_search',keywords:['润唇'],excludeIdentities:['original-creator'],excludeContacts:['original-contact']},preferSavedDiscovery:true});
 assert.equal(result.sourceDiscoveryMode,'structured_browse');
 assert.deepEqual(result.keywords,[]);
 assert.equal(result.maximumFollowers,0);
 assert.deepEqual(result.excludeIdentities,['original-creator']);
 assert.deepEqual(result.excludeContacts,['original-contact']);
});

test('切换发现类目保留同一手卡的内容适配范围，修改手卡重新建立范围',()=>{
 const {preserveContentFitCategory}=require('./collection-strategy-runtime.cjs');
 const old={brief:'护唇与日常好物',category:'美妆个护'};
 const switched=preserveContentFitCategory({brief:old.brief,category:'个护家清'},old);
 assert.equal(switched.category,'个护家清');assert.equal(switched.contentFitCategory,'美妆个护');
 assert.equal(preserveContentFitCategory({brief:'数码项目',category:'数码'},old).contentFitCategory,'数码');
});
