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


test("Jev uncertainty keeps reviewed candidates at content review", () => {
  const creator=normalizeCreator({content_evidence_reviewed:true,
    jev_analysis:{advisory_only:false,route:"uncertain"},precontact_reason:"Jev：证据不足"});
  assert.equal(creator.stage,"内容复核");
  assert.ok(creator.evidence.includes("Jev：证据不足"));
});


test("原生采集记录详情保留截图和联系人采证来源时间", () => {
  const c = normalizeCreator({evidence_screenshots:["/evidence/work.jpg", "", null], buyin_contact_source:"buyin_profile_ui_contact_icon", ui_contact_channels_checked_at:"2026-10-09T03:00:00", ui_contact_probe_at:"2026-10-09T02:59:00"});
  assert.equal(c.evidenceScreenshot,"/evidence/work.jpg");
  assert.equal(c.contactSource,"buyin_profile_ui_contact_icon");
  assert.equal(c.contactAcquiredAt,"2026-10-09T03:00:00");
  const missing = normalizeCreator({evidence_screenshots:[], updated_at:"2026-10-09"});
  assert.equal(missing.evidenceScreenshot,"");
  assert.equal(missing.contactAcquiredAt,"");
});

test("人工和交付字段优先于原始采证字段", () => {
  const c = normalizeCreator({"内容证据截图":"/saved/review.jpg", evidence_screenshots:["/old/work.jpg"], "联系方式来源":"人工复核", buyin_contact_source:"raw", "联系方式获取时间":"2026-10-08", ui_contact_probe_at:"2026-10-07"});
  assert.equal(c.evidenceScreenshot,"/saved/review.jpg");
  assert.equal(c.contactSource,"人工复核");
  assert.equal(c.contactAcquiredAt,"2026-10-08");
});

test("精选联盟已保存证据在详情展示来源，显式作品正文优先，缺失不伪造", () => {
 const raw={content_evidence:["#润唇膏 使用体验","某品牌润唇膏3g"]};
 assert.equal(normalizeCreator(raw).contentText,"精选联盟已保存内容证据（含作品标题与商品名）：\n#润唇膏 使用体验 | 某品牌润唇膏3g");
 assert.equal(normalizeCreator({"内容证据":"旧交付作品证据"}).contentText,"精选联盟已保存内容证据（含作品标题与商品名）：\n旧交付作品证据");
 assert.equal(normalizeCreator({...raw,"作品文字与近期内容":"原正文"}).contentText,"原正文");
 assert.equal(normalizeCreator({}).contentText,"");
 assert.deepEqual(raw.content_evidence,["#润唇膏 使用体验","某品牌润唇膏3g"]);
});

test("达人经营资料保留真实平台区间与零视频，缺失不伪造零", () => {
 const row={city:"山西·太原",monthly_sales_low:10000,monthly_sales_high:25000,monthly_sales_value:10000,video_count_30d:0,main_sale_type:"纯短视频",profile_text:"简介",douyin_content_text:"近期作品"};
 const c=normalizeCreator(row);
 assert.equal(c.city,row.city); assert.equal(c.monthlySalesLow,10000); assert.equal(c.monthlySalesHigh,25000);
 assert.equal(c.videoCount30d,0); assert.equal(c.mainSaleType,"纯短视频"); assert.equal(c.contentText,"近期作品");
 assert.equal(normalizeCreator({}).videoCount30d,undefined); assert.equal(normalizeCreator({}).monthlySalesLow,undefined);
 assert.equal(row.monthly_sales_high,25000);
});
