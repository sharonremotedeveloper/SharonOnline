/**
 * Country choices for sign-up and profiles (ISO 3166-1 alpha-2, what the API stores). Names come from the browser
 * (Intl.DisplayNames) so the list needs no translation table. The country used to be a free-text box that defaulted to
 * "US" for anyone outside a few time zones (a Mauritius user was stored as US).
 */
export const COUNTRY_CODES = (
  "AD AE AF AG AI AL AM AO AR AT AU AW AZ BA BB BD BE BF BG BH BI BJ BM BN BO BR BS BT BW BY BZ CA CD CF CG CH CI CL " +
  "CM CN CO CR CU CV CY CZ DE DJ DK DM DO DZ EC EE EG ER ES ET FI FJ FM FR GA GB GD GE GH GM GN GQ GR GT GW GY HK HN " +
  "HR HT HU ID IE IL IN IQ IR IS IT JM JO JP KE KG KH KI KM KN KP KR KW KY KZ LA LB LC LI LK LR LS LT LU LV LY MA MC " +
  "MD ME MG MH MK ML MM MN MO MR MT MU MV MW MX MY MZ NA NE NG NI NL NO NP NR NZ OM PA PE PG PH PK PL PR PS PT PW PY " +
  "QA RO RS RU RW SA SB SC SD SE SG SI SK SL SM SN SO SR SS ST SV SY SZ TD TG TH TJ TL TM TN TO TR TT TV TW TZ UA UG " +
  "US UY UZ VA VC VE VN VU WS YE ZA ZM ZW"
).split(" ");

/** Our main markets first, then everyone else alphabetically by English name. */
const PRIORITY = ["JP", "KR", "ZA", "DE", "FR", "GB", "MU"];

export function countryName(code: string): string {
  try {
    return new Intl.DisplayNames(["en"], { type: "region" }).of(code) ?? code;
  } catch {
    return code;
  }
}

export function countryOptions(): { value: string; label: string }[] {
  const rest = COUNTRY_CODES.filter((c) => !PRIORITY.includes(c))
    .map((value) => ({ value, label: countryName(value) }))
    .sort((a, b) => a.label.localeCompare(b.label));
  return [...PRIORITY.map((value) => ({ value, label: countryName(value) })), ...rest];
}

const ZONE_COUNTRY: Record<string, string> = {
  "Asia/Tokyo": "JP", "Asia/Seoul": "KR", "Africa/Johannesburg": "ZA", "Indian/Mauritius": "MU",
  "Europe/Berlin": "DE", "Europe/Paris": "FR", "Europe/London": "GB", "Europe/Madrid": "ES", "Europe/Rome": "IT",
  "Europe/Amsterdam": "NL", "Europe/Brussels": "BE", "Europe/Zurich": "CH", "Europe/Vienna": "AT",
  "Europe/Stockholm": "SE", "Europe/Oslo": "NO", "Europe/Copenhagen": "DK", "Europe/Helsinki": "FI",
  "Europe/Warsaw": "PL", "Europe/Lisbon": "PT", "Europe/Dublin": "IE", "Europe/Prague": "CZ", "Europe/Athens": "GR",
  "Europe/Budapest": "HU", "Asia/Shanghai": "CN", "Asia/Taipei": "TW", "Asia/Hong_Kong": "HK",
  "Asia/Singapore": "SG", "Asia/Dubai": "AE", "Asia/Kolkata": "IN", "Asia/Bangkok": "TH",
  "Asia/Ho_Chi_Minh": "VN", "Asia/Manila": "PH", "Asia/Jakarta": "ID",
};

/**
 * Best guess at the user's country, or "" (the form then asks). Time zone first (where they are), then the browser
 * locale's region (how their device is set up). Never a silent default country.
 */
export function guessCountry(timeZone: string | undefined, locales: readonly string[] = []): string {
  if (timeZone && ZONE_COUNTRY[timeZone]) return ZONE_COUNTRY[timeZone];
  if (timeZone?.startsWith("America/") && !timeZone.includes("Argentina") && !timeZone.includes("Sao_Paulo")) {
    // Most America/* zones are US or Canada; the locale decides between them, else ask.
    const region = regionOf(locales);
    if (region === "US" || region === "CA") return region;
  }
  if (timeZone?.startsWith("Australia/")) return "AU";
  const region = regionOf(locales);
  return region && COUNTRY_CODES.includes(region) ? region : "";
}

function regionOf(locales: readonly string[]): string {
  for (const locale of locales) {
    const match = /^[a-z]{2,3}[-_]([A-Z]{2})\b/i.exec(locale);
    if (match) return match[1].toUpperCase();
  }
  return "";
}
