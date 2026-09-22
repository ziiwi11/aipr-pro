function collectDeliveredIdentities(deliveries = []) {
  const identities = new Set();
  for (const delivery of deliveries) {
    for (const row of delivery?.rows || delivery?.candidates || []) {
      for (const value of [
        row?.["主页身份ID"], row?.["抖音号"], row?.identity, row?.buyin_uid,
        row?.douyin_id, row?.author_id, row?.sec_uid,
      ]) {
        const clean = String(value || "").trim();
        if (clean) identities.add(clean);
      }
    }
  }
  return [...identities];
}

module.exports = { collectDeliveredIdentities };
