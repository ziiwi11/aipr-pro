const test = require("node:test");
const assert = require("node:assert/strict");

let displayDouyin;
let unavailableCreators;
let isOutreachEligible;
let selectableCreators;
let previewSummary;
let canStartBatch;

test.before(async () => {
  ({ displayDouyin, unavailableCreators, isOutreachEligible, selectableCreators, previewSummary, canStartBatch } = await import("../frontend/src/public/aipr-ai-outreach.js"));
});

test("只有含微信或手机号的达人可被批量选择", () => {
  const creators = [
    { id: "a", wechat: "wx_a" },
    { id: "b", phone: "13800138000" },
    { id: "c", plainContact: "" },
    { id: "d", email: "only@example.test" },
  ];

  assert.equal(isOutreachEligible(creators[0]), true);
  assert.equal(isOutreachEligible(creators[2]), false);
  assert.deepEqual(selectableCreators(creators).map((item) => item.id), ["a", "b"]);
});

test("授权预览文案显示有效、缺失和重复数量", () => {
  assert.equal(previewSummary({ selectedCount: 8, validCount: 5, missingCount: 2, duplicateCount: 1 }), "已选 8 · 可同步 5 · 缺失 2 · 重复 1 · 当前发送 0");
});

test("只有同步完成并勾选二次确认的批次可启动", () => {
  assert.equal(canStartBatch({ status: "authorized" }, true), false);
  assert.equal(canStartBatch({ status: "synced" }, false), false);
  assert.equal(canStartBatch({ status: "synced" }, true), true);
});

test('unavailable outreach records explain email-only and absent-contact limitations',()=>{
 assert.deepEqual(unavailableCreators([{name:'邮箱达人',email:'someone@example.test',plainContact:'someone@example.test'},{name:'无联系'},{name:'可联系',wechat:'testwx'}]),[{name:'邮箱达人',reason:'仅有邮箱，雷神建联需要微信或手机号'},{name:'无联系',reason:'缺少可用微信或手机号'}]);
});

test("建联显示真实抖音号并隐藏内部身份串",()=>{assert.equal(displayDouyin({douyinId:"44591272",douyin:"v2_"+"a".repeat(80)}),"44591272");assert.equal(displayDouyin({douyin:"v2_"+"a".repeat(80)}),"抖音号未记录 · 详情见达人优选");});
