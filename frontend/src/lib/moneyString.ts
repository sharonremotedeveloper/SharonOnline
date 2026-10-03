/**
 * Exact money strings from the API ("162.00") - never parsed to float. Sums are done in integer minor units.
 */
const PATTERN = /^(-?)(\d+)(?:\.(\d+))?$/;

function parts(value: string, decimals: number): { negative: boolean; units: bigint } {
  const m = PATTERN.exec(value.trim());
  if (!m) throw new Error(`Not a money string: ${JSON.stringify(value)}`);
  const frac = (m[3] ?? "").padEnd(decimals, "0").slice(0, decimals);
  return { negative: m[1] === "-", units: BigInt(m[2] + frac) };
}

/** Sum money strings exactly; returns a string with `decimals` places. */
export function sumMoney(values: string[], decimals = 2): string {
  let total = BigInt(0);
  for (const v of values) {
    const { negative, units } = parts(v, decimals);
    total += negative ? -units : units;
  }
  return fromUnits(total, decimals);
}

function fromUnits(total: bigint, decimals: number): string {
  const negative = total < BigInt(0);
  const digits = (negative ? -total : total).toString().padStart(decimals + 1, "0");
  const whole = digits.slice(0, digits.length - decimals);
  const frac = decimals ? "." + digits.slice(digits.length - decimals) : "";
  return (negative ? "-" : "") + whole + frac;
}

/** Group thousands with a comma: "1234567.50" -> "1,234,567.50". Pure string work. */
export function groupMoney(value: string, decimals = 2): string {
  const { negative, units } = parts(value, decimals);
  const s = fromUnits(units, decimals);
  const [whole, frac] = s.split(".");
  const grouped = whole.replace(/\B(?=(\d{3})+(?!\d))/g, ",");
  return (negative ? "-" : "") + grouped + (frac ? "." + frac : "");
}
