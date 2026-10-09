function mergeRuntimeCollectionStrategy({ base = {}, existing = {}, deliveredIdentities = [], deliveredContacts = [], ownDeliveredContacts = [], ownDeliveredIdentities = [], preferSavedDiscovery = false } = {}) {
  if (preferSavedDiscovery && base.sourceDiscoveryMode) existing = { ...existing, sourceDiscoveryMode: base.sourceDiscoveryMode };
  const excludeIdentities = [...new Set([
    ...(existing.excludeIdentities || []),
    ...(base.excludeIdentities || []),
    ...deliveredIdentities,
  ].map((value) => String(value || "").trim()).filter(Boolean))];
  const foreignContacts=new Set(deliveredContacts.map(value=>String(value).trim().toLowerCase()));
  const ownContacts=new Set(ownDeliveredContacts.map(value=>String(value).trim().toLowerCase()));
  const foreignIds=new Set(deliveredIdentities.map(value=>String(value).trim()));
  const ownIds=new Set(ownDeliveredIdentities.map(value=>String(value).trim()));
  const excludeContacts = [...new Set([
    ...(existing.excludeContacts || []),
    ...(base.excludeContacts || []),
    ...deliveredContacts,
  ].map((value) => String(value || "").trim()).filter(value=>value&&(!ownContacts.has(value.toLowerCase())||foreignContacts.has(value.toLowerCase()))))];
  const deliveryIds=(existing.deliveryExcludeIdentities ?? base.deliveryExcludeIdentities ?? excludeIdentities).filter(value=>!ownIds.has(String(value).trim())||foreignIds.has(String(value).trim()));
  const merged = {
    ...base,
    excludeIdentities,
    excludeContacts,
    deliveryExcludeIdentities: deliveryIds,
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

  if (existing.sourceDiscoveryMode === "keyword_search") {
    merged.sourceDiscoveryMode = "keyword_search";
    merged.keywords = [...new Set([...(existing.keywords || []), ...(base.keywords || [])]
      .map((value) => String(value || "").trim()).filter(Boolean))];
  }

  for (const key of ["replenishmentRound", "evidenceLanesPerShop", "maxReplenishmentRounds"]) {
    const value = existing[key] ?? base[key];
    if (value !== undefined && value !== null && value !== "") merged[key] = Number(value);
  }
  return merged;
}

module.exports = { mergeRuntimeCollectionStrategy };

// The strategy form saves before starting. A rendered button can still hold
// its older task snapshot; persisted task settings are the source of truth.
function savedStartStrategy(savedTask = {}, supplied = {}) {
  return savedTask.collectionStrategy && Object.keys(savedTask.collectionStrategy).length
    ? savedTask.collectionStrategy : supplied;
}
module.exports.savedStartStrategy = savedStartStrategy;

function preserveContentFitCategory(base={}, baseline={}) {
 const category=String(base.contentFitCategory || ((baseline.brief && baseline.brief===base.brief) ? baseline.contentFitCategory || baseline.category : "") || base.category || "");
 return {...base, contentFitCategory:category};
}
module.exports.preserveContentFitCategory=preserveContentFitCategory;
