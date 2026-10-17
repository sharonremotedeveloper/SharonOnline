import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { COUNTRY_CODES, countryOptions, guessCountry } from "./countries";

describe("country choices", () => {
  it("guesses from the time zone first (Mauritius was stored as US)", () => {
    assert.equal(guessCountry("Indian/Mauritius", ["en-US"]), "MU");
    assert.equal(guessCountry("Asia/Tokyo"), "JP");
    assert.equal(guessCountry("Africa/Johannesburg"), "ZA");
    assert.equal(guessCountry("Europe/Paris"), "FR");
  });

  it("uses the locale region for ambiguous zones and never invents a country", () => {
    assert.equal(guessCountry("America/Toronto", ["en-CA"]), "CA");
    assert.equal(guessCountry("America/Chicago", ["fr"]), "");
    assert.equal(guessCountry("Pacific/Fiji", ["en-FJ"]), "FJ");
    assert.equal(guessCountry(undefined, []), "");
    assert.equal(guessCountry("Etc/UTC", ["xx-ZZ"]), "");
  });

  it("lists every code once with our markets first", () => {
    const options = countryOptions();
    assert.equal(options.length, COUNTRY_CODES.length);
    assert.equal(new Set(options.map((o) => o.value)).size, COUNTRY_CODES.length);
    assert.deepEqual(options.slice(0, 3).map((o) => o.value), ["JP", "KR", "ZA"]);
    assert.ok(options.every((o) => /^[A-Z]{2}$/.test(o.value) && o.label.length > 0));
  });
});
