function normalizeDelivery(delivery = {}) {
  const rows = Array.isArray(delivery.rows) ? delivery.rows : [];
  const candidateCreators = rows.map((row, index) => normalizeCreator(row, index));
  const creators = candidateCreators.filter((item) => Boolean(item.plainContact));
  const plainContacts = numberOr(delivery.plain_contact_count, creators.filter((item) => item.plainContact).length);
  const wechat = numberOr(delivery.wechat_contact_count, creators.filter((item) => item.wechat).length);
  const phone = numberOr(delivery.phone_contact_count, creators.filter((item) => item.phone).length);

  return {
    creators,
    candidateCreators,
    metrics: {
      targetCount: numberOr(delivery.target_count, candidateCreators.length),
      candidates: candidateCreators.length,
      plainContacts,
      wechat,
      phone,
      remaining: numberOr(delivery.pending_contact_count, Math.max(0, creators.length - plainContacts)),
    },
  };
}

function normalizeCreator(row = {}, index = 0) {
  const evidenceObject = parseEvidence(row["验证证据"]);
  const score = clamp(numberOr(row["综合评分"] ?? row.score, evidenceObject.score || 0), 0, 100);
  const normalizedSignal = score / 100;
  const riskTags = splitTags(row["风险标签"] || row.risk_tags || row.category || row.categories);
  const wechat = validPlainContact(row["微信"] || row.buyin_contact_wechat || row.cart_contact_wechat || row.wechat);
  const phone = validPlainContact(row["手机号"] || row.buyin_contact_phone || row.cart_contact_phone || row.phone);
  const email = validPlainContact(row["邮箱"] || row.buyin_contact_email || row.cart_contact_email || row.email);
  const explicit = validPlainContact(row["明文联系方式"]);
  const legacy = recognizableLegacyContact(row["联系方式"]);
  const contact = explicit || wechat || phone || email || legacy;
  const status = String(row["目标状态"] || "");
  const homepage = String(row["抖音主页"] || row.douyin_homepage || "").trim();
  const identity = String(row["主页身份ID"] || row.identity || row.buyin_uid || row.douyin_id || evidenceObject.buyin_account_id || "").trim();
  const reviewState = parseReviewState(row);
  const jev = row.jev_analysis || parseEvidence(row["Jev内容复核"]);
  const jevPending = jev.advisory_only === false && ["uncertain", "review_conflict"].includes(jev.route);
  const jevReason = row.precontact_reason || jev.reason || "";

  return {
    id: identity || `delivery-${index + 1}`,
    name: decodeEntities(String(row["达人昵称"] || row.nickname || evidenceObject.buyin_nickname || `达人 ${index + 1}`)),
    douyin: identity || "待补抖音号",
    nickname: decodeEntities(String(row["达人昵称"] || row.nickname || evidenceObject.buyin_nickname || `达人 ${index + 1}`)),
    douyinId: String(row["抖音号"] || row.douyin_id || row.unique_id || identity).trim(),
    fans: numberOr(row["粉丝数"] ?? row.fans, 0),
    talentLevel: parseLevel(evidenceObject.buyin_level || row["达人等级"] || row["等级"] || row.author_level || row.talent_level),
    category: String(row["类目"] || row.category || row.main_category || (Array.isArray(row.categories) ? row.categories.join("/") : row.categories) || "").trim(),
    douyinHomepage: homepage,
    buyinHomepage: String(row["精选联盟主页"] || row.buyin_profile_url || "").trim(),
    level: parseLevel(evidenceObject.buyin_level || row["达人等级"] || row["等级"] || row.author_level || row.talent_level),
    qualityLevel: String(row["等级"] || "").trim(),
    city: String(row.city || row["城市"] || "").trim(),
    mainSaleType: String(row.main_sale_type || row.mainSaleType || row["主要带货方式"] || "").trim(),
    videoCount30d: optionalNumber(row.video_count_30d ?? row.videoCount30d ?? row["近30天视频数"]),
    monthlySalesLow: optionalNumber(row.monthly_sales_low ?? row.monthlySalesLow ?? row["平台月销区间下界"]),
    monthlySalesHigh: optionalNumber(row.monthly_sales_high ?? row.monthlySalesHigh ?? row["平台月销区间上界"]),
    monthlySalesLowerBound: optionalNumber(row.monthly_sales_value),
    monthlySalesDisplay: String(row["历史销售额"] || row["销售额"] || evidenceObject.monthly_sales || ""),
    profileText: String(row.profile_text || row["达人简介与平台资料"] || ""),
    contentText: String(row.douyin_content_text || row["作品文字与近期内容"] || savedContentText(row)),
    contentEvidenceSource: String(row.content_evidence_source || row["作品证据来源"] || ""),
    evidenceReviewedAt: String(row.evidence_reviewed_at || row["作品复核时间"] || ""),
    contactEvidence: row.ui_contact_evidence || {},
    libraryStatus: String(row.ui_add_library_status || row["平台入库状态"] || ""),
    sourceDiscoveryMode: String(row.source_discovery_mode || ""),
    sales: parseMonthlySales(evidenceObject.monthly_sales || row["历史销售额"] || row["销售额"]),
    followers: formatFollowers(row["粉丝数"] ?? row.fans),
    categories: riskTags.length ? riskTags : splitTags(evidenceObject.category || row["品牌/内容证据"]),
    verifiedHomepage: Boolean(homepage || identity),
    evidenceReviewed: reviewState.evidenceReviewed,
    signals: { persona: normalizedSignal, content: normalizedSignal, sales: normalizedSignal, scene: normalizedSignal, price: normalizedSignal },
    sourceScore: score,
    reason: String(row["推荐理由"] || row.precontact_reason || jev.reason || row.realtime_flow_reason || ""),
    decision: String(row["推荐结论"] || row.precontact_state || ""),
    jevAnalysis: jev,
    contentEvidence: row["内容证据"] || row.content_evidence || evidenceObject,
    evidenceScreenshot: String(row["内容证据截图"] || row.content_evidence_screenshot || (Array.isArray(row.evidence_screenshots) ? row.evidence_screenshots.filter(value => typeof value === "string" && value.trim()).join("\n") : "")),
    flowState: String(row.realtime_flow_state || ""),
    flowReason: String(row.realtime_flow_reason || ""),
    contactSource: String(row["联系方式来源"] || row.contact_source || row.buyin_contact_source || row.cart_contact_source || ""),
    contactAcquiredAt: String(row.contact_acquired_at || row["联系方式获取时间"] || row.ui_contact_channels_checked_at || row.ui_contact_probe_at || ""),
    contactCorrectedAt: String(row.contact_corrected_at || row["联系方式修订时间"] || ""),
    plainContact: contact,
    wechat,
    phone,
    email,
    contact: contact ? (wechat ? "微信已获取" : phone ? "手机号已获取" : "联系方式已获取") : "待获取",
    stage: jevPending ? "内容复核" : contact ? "待建联" : reviewState.evidenceReviewed ? "联系方式" : "视觉复核",
    shop: String(row["分跑店铺"] || row.shop || "").trim(),
    evidence: [evidenceText(row, evidenceObject), jevReason].filter(Boolean).join("；"),
    risk: String(row["风险标签"] || "暂无额外风险标签").trim(),
    sourceStatus: String(row["联系方式状态"] || row["联系方式提取状态"] || "").trim(),
  };
}

function savedContentText(row) {
  const evidence = row["内容证据"] || row.content_evidence;
  const text = Array.isArray(evidence) ? evidence.filter(value => typeof value === "string" && value.trim()).join(" | ") : typeof evidence === "string" ? evidence.trim() : "";
  return text ? "精选联盟已保存内容证据（含作品标题与商品名）：\n" + text : "";
}

function validPlainContact(value) {
  const text = String(value || "").trim();
  if (!text || /[*•]|隐藏|未授权|待获取|待补|暂无|不可见/u.test(text)) return "";
  return text;
}

function recognizableLegacyContact(value) {
  const text = validPlainContact(value);
  if (!text) return "";
  if (/1[3-9]\d{9}/u.test(text)) return text;
  if (/[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}/u.test(text)) return text;
  if (/微信\s*[:：]\s*[A-Za-z][A-Za-z0-9_-]{5,19}/u.test(text)) return text;
  return "";
}

function parseReviewState(row = {}) {
  const status = String(row["目标状态"] || "").trim();
  const conclusion = String(row["验证结论"] || "").trim();
  const evidenceReviewed = row.content_evidence_reviewed === true || status.includes("已验证") ||
    /(?:审核|复核|验证)通过|已人工复核|已完成(?:审核|复核|验证)/u.test(conclusion);
  return { evidenceReviewed };
}

function parseEvidence(value) {
  if (!value || typeof value !== "string") return {};
  try {
    const parsed = JSON.parse(value);
    return parsed && typeof parsed === "object" ? parsed : {};
  } catch {
    return {};
  }
}

function evidenceText(row, evidenceObject) {
  if (Object.keys(evidenceObject).length) {
    return [evidenceObject.category, evidenceObject.monthly_sales && `月销 ${evidenceObject.monthly_sales}`, row["验证结论"]]
      .filter(Boolean).join("；");
  }
  return String(row["验证证据"] || row["品牌/内容证据"] || row["验证结论"] || "待补充内容证据").trim();
}

function parseLevel(value) {
  const match = String(value || "").match(/(?:LV)?\s*([1-4])/i);
  return match ? Number(match[1]) : 1;
}

function parseMonthlySales(value) {
  const first = String(value || "").toLowerCase().replace(/,/g, "").split(/[-~至]/)[0].trim();
  if (!first) return 0;
  const match = first.match(/([\d.]+)\s*(w|万)?/i);
  if (!match) return 0;
  return Math.round(Number(match[1]) * (match[2] ? 10000 : 1));
}

function splitTags(value) {
  return String(value || "").split(/[\/、,，;；|]/).map((item) => item.replace(/风险$/u, "").trim()).filter(Boolean);
}

function formatFollowers(value) {
  const numeric = Number(value);
  if (!Number.isFinite(numeric) || numeric <= 0) return "待补";
  return numeric >= 10000 ? `${(numeric / 10000).toFixed(1)}万` : String(numeric);
}

function decodeEntities(value) {
  return value.replace(/&amp;/g, "&").replace(/&lt;/g, "<").replace(/&gt;/g, ">").replace(/&quot;/g, '"');
}

function optionalNumber(value) {
  if (value === undefined || value === null || value === "") return undefined;
  const number = Number(value);
  return Number.isFinite(number) && number >= 0 ? number : undefined;
}

function numberOr(value, fallback) {
  const numeric = Number(value);
  return Number.isFinite(numeric) ? numeric : fallback;
}

function clamp(value, minimum, maximum) {
  return Math.min(maximum, Math.max(minimum, value));
}

module.exports = { normalizeDelivery, normalizeCreator, parseMonthlySales, parseReviewState };
