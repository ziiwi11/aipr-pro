function collectionEventStatus(payload, workerLive) {
  if (payload.workerAction !== "collect-creators" || !workerLive) return null;
  if (payload.type === "error" && payload.status === "shop_error") return "running";
  if (payload.type === "progress" && ["collection_started", "collection_retry_scheduled", "platform_filters_confirmed"].includes(payload.status)) return "running";
  return null;
}
module.exports = { collectionEventStatus };
