function mergeRuntimeCollectionStrategy({ base = {}, existing = {}, deliveredIdentities = [] } = {}) {
  const excludeIdentities = [...new Set([
    ...(existing.excludeIdentities || []),
    ...(base.excludeIdentities || []),
    ...deliveredIdentities,
  ].map((value) => String(value || "").trim()).filter(Boolean))];
  const excludeContacts = [...new Set([
    ...(existing.excludeContacts || []),
    ...(base.excludeContacts || []),
  ].map((value) => String(value || "").trim()).filter(Boolean))];
  const merged = {
    ...base,
    excludeIdentities,
    excludeContacts,
    realtimeCreatorFlow: true,
    contactDedupMode: "strict-any-plaintext-value",
  };

  if (existing.sourceDiscoveryMode === "structured_browse") {
    for (const key of [
      "sourceDiscoveryMode", "sourceBrowseProfileId", "sourceBrowseMaxPages",
      "sourceBrowsePagesPerRun", "sourceProfileCategoryStrict", "minimumVideos30d",
    ]) {
      if (existing[key] !== undefined) merged[key] = existing[key];
    }
    merged.keywords = [];
  }

  for (const key of ["replenishmentRound", "evidenceLanesPerShop", "maxReplenishmentRounds"]) {
    const value = existing[key] ?? base[key];
    if (value !== undefined && value !== null && value !== "") merged[key] = Number(value);
  }
  return merged;
}

module.exports = { mergeRuntimeCollectionStrategy };
