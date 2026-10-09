const METRIC_FIELDS = ["collected", "processed", "plainContacts", "wechat", "phone"];

function mergeTaskHighWater(previous = {}, incoming = {}) {
  const merged = { ...previous, ...incoming };
  for (const field of METRIC_FIELDS) {
    merged[field] = Math.max(number(previous[field]), number(incoming[field]));
  }

  const target = Math.max(1, number(merged.targetCount) || 1);
  const derivedRemaining = Math.max(0, target - merged.plainContacts);
  const previousRemaining = finiteNumber(previous.remaining);
  const incomingRemaining = finiteNumber(incoming.remaining);
  merged.remaining = Math.min(
    previousRemaining ?? derivedRemaining,
    incomingRemaining ?? derivedRemaining,
    derivedRemaining,
  );
  return merged;
}

function mergeTaskDeliverySnapshot(previous = {}, incoming = {}, { preserveTarget = false } = {}) {
  const merged = mergeTaskHighWater(previous, incoming);
  for (const field of ["targetCount", "plainContacts", "wechat", "phone", "remaining"]) {
    if (preserveTarget && ["targetCount", "remaining"].includes(field)) continue;
    if (finiteNumber(incoming[field]) !== null) merged[field] = number(incoming[field]);
  }
  if (preserveTarget) {
    merged.targetCount = previous.targetCount;
    merged.remaining = Math.max(0, number(previous.targetCount) - merged.plainContacts);
  }
  return merged;
}

function number(value) {
  const parsed = Number(value);
  return Number.isFinite(parsed) && parsed >= 0 ? parsed : 0;
}

function finiteNumber(value) {
  const parsed = Number(value);
  return Number.isFinite(parsed) && parsed >= 0 ? parsed : null;
}

module.exports = { mergeTaskDeliverySnapshot, mergeTaskHighWater };
