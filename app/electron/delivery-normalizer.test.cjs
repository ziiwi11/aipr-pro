const test = require("node:test");
const assert = require("node:assert/strict");

const { normalizeDelivery, normalizeCreator } = require("./delivery-normalizer.cjs");

test("待近期内容证据审核不会被标记为已审核", () => {
  const creator = normalizeCreator({
    主页身份ID: "creator-1",
    抖音主页: "https://example.test/creator-1",
    验证结论: "待近期内容证据审核",
  });

  assert.equal(creator.verifiedHomepage, true);
  assert.equal(creator.evidenceReviewed, false);
  assert.equal(creator.stage, "视觉复核");
});

test("明确通过审核的达人进入联系方式阶段", () => {
  const creator = normalizeCreator({
    主页身份ID: "creator-2",
    抖音主页: "https://example.test/creator-2",
    验证结论: "人工复核通过",
  });

  assert.equal(creator.verifiedHomepage, true);
  assert.equal(creator.evidenceReviewed, true);
  assert.equal(creator.stage, "联系方式");
});

test("有明文联系方式的达人进入待建联阶段", () => {
  const creator = normalizeCreator({
    主页身份ID: "creator-3",
    验证结论: "审核通过",
    微信: "wx_creator_3",
    明文联系方式: "wx_creator_3",
  });

  assert.equal(creator.stage, "待建联");
  assert.equal(creator.plainContact, "wx_creator_3");
});

test("联系方式入口可见但没有明文的候选不会进入正式名单", () => {
  const delivery = normalizeDelivery({
    target_count: 1000,
    rows: [
      { 主页身份ID: "candidate-1", 联系方式状态: "平台显示有联系方式" },
      { 主页身份ID: "listed-1", 微信: "wx_listed_1", 明文联系方式: "wx_listed_1" },
    ],
  });

  assert.equal(delivery.candidateCreators.length, 2);
  assert.equal(delivery.creators.length, 1);
  assert.equal(delivery.creators[0].id, "listed-1");
  assert.equal(delivery.metrics.candidates, 2);
  assert.equal(delivery.metrics.plainContacts, 1);
});

test("遮罩联系方式不会进入正式名单", () => {
  const delivery = normalizeDelivery({
    rows: [{ 主页身份ID: "masked-1", 明文联系方式: "138****0000" }],
  });

  assert.equal(delivery.candidateCreators.length, 1);
  assert.equal(delivery.creators.length, 0);
  assert.equal(delivery.metrics.plainContacts, 0);
});

test("逐人流水线的后端字段可直接显示为正式达人", () => {
  const creator = normalizeCreator({
    identity: "backend-1",
    nickname: "实时达人",
    douyin_id: "douyin_backend_1",
    category: "美妆",
    buyin_profile_url: "https://example.test/backend-1",
    buyin_contact_wechat: "wx_backend_1",
    content_evidence_reviewed: true,
  });

  assert.equal(creator.id, "backend-1");
  assert.equal(creator.name, "实时达人");
  assert.equal(creator.douyin, "backend-1");
  assert.equal(creator.wechat, "wx_backend_1");
  assert.equal(creator.stage, "待建联");
});
