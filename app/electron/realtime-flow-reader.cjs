const {readCachedJson}=require("./cached-file.cjs");
const fs = require("node:fs");
const path = require("node:path");

const SUITABLE_STATES = new Set(["suitable", "contact_revealing", "plaintext_unique", "listed"]);

function readRealtimeCreatorFlow(outputDir) {
  const flowPath = outputDir ? path.join(String(outputDir), "aipr_realtime_creator_flow.json") : "";
  if (!flowPath || !fs.existsSync(flowPath)) return emptySnapshot(flowPath);
  try {
    const payload = readCachedJson(flowPath);
    const records = Array.isArray(payload.records)
      ? payload.records.filter((record) => record && typeof record === "object" && record.row && typeof record.row === "object")
      : [];
    const candidateRows = records.map((record) => ({ ...record.row, realtime_flow_state: record.state, realtime_flow_reason: record.reason || "" }));
    let formalRows = records
      .filter((record) => record.state === "listed" && hasPlaintext(record.row))
      .map((record) => ({ ...record.row, realtime_flow_state: record.state, realtime_flow_reason: record.reason || "" }));
    const strictPath = path.join(String(outputDir), "aipr_strict_contact_highwater.json");
    if (fs.existsSync(strictPath)) {
      // The audited delivery list is authoritative; flow state is processing history.
      const strict = readCachedJson(strictPath);
      formalRows = Array.isArray(strict.candidates)
        ? strict.candidates.filter((row) => row && typeof row === "object" && hasPlaintext(row))
          .map((row) => ({ ...row, realtime_flow_state: "listed" }))
        : [];
    }
    return {
      available: true,
      path: flowPath,
      updatedAt: payload.updated_at || "",
      records,
      candidateRows,
      formalRows,
      metrics: {
        candidates: records.length,
        suitable: records.filter((record) => SUITABLE_STATES.has(record.state)).length,
        contactRevealing: records.filter((record) => record.state === "contact_revealing").length,
        plaintext: records.filter((record) => hasPlaintext(record.row)).length,
        listed: formalRows.length,
        wechat: formalRows.filter((row) => [row.buyin_contact_wechat, row.cart_contact_wechat, row.wechat, row["微信"]].some(validPlaintext)).length,
        phone: formalRows.filter((row) => [row.buyin_contact_phone, row.cart_contact_phone, row.phone, row["手机号"]].some(validPlaintext)).length,
        rejected: records.filter((record) => [
          "duplicate_identity", "unsuitable", "insufficient_evidence", "not_authorized",
          "not_available", "duplicate_contact", "error",
        ].includes(record.state)).length,
      },
    };
  } catch (error) {
    return { ...emptySnapshot(flowPath), error: error.message };
  }
}

function hasPlaintext(row = {}) {
  return [
    row.buyin_contact_wechat, row.cart_contact_wechat, row.wechat, row["微信"],
    row.buyin_contact_phone, row.cart_contact_phone, row.phone, row["手机号"],
    row.buyin_contact_email, row.cart_contact_email, row.email, row["邮箱"],
  ].some(validPlaintext);
}

function validPlaintext(value) {
  const text = String(value || "").trim();
  return Boolean(text) && !/[*•]|隐藏|未授权|待获取|待补|暂无|不可见/u.test(text);
}

function emptySnapshot(flowPath = "") {
  return {
    available: false,
    path: flowPath,
    updatedAt: "",
    records: [],
    candidateRows: [],
    formalRows: [],
    metrics: { candidates: 0, suitable: 0, contactRevealing: 0, plaintext: 0, listed: 0, rejected: 0 },
  };
}

module.exports = { readRealtimeCreatorFlow, hasPlaintext };
