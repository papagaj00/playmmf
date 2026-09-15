export function formatPoints(value) {
  const numericValue = Number(value);
  if (!Number.isFinite(numericValue)) return "0";
  return Math.round(numericValue).toLocaleString("cs-CZ");
}
