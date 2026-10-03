/**
 * Tests for money formatting. The API sends amounts as decimal STRINGS; they must never pass through a float.
 */
import { describe, it } from "node:test";
import assert from "node:assert/strict";

import {
  formatMoney,
  lessonPriceFor,
  formatLessonPrice,
  dividePrice,
  currencyDecimals,
  formatPackPrice,
  formatPackPerLesson,
  type LessonPrice,
  type CreditPackPrice,
} from "./prices";

describe("formatMoney", () => {
  it("formats USD and EUR with 2 decimals", () => {
    assert.equal(formatMoney("9.00", "USD", 2), "$9.00");
    assert.equal(formatMoney("8.50", "EUR", 2), "€8.50");
  });

  it("formats ZAR with 2 decimals and the R symbol", () => {
    const out = formatMoney("162.00", "ZAR", 2);
    assert.match(out, /^R\s?162\.00$/);
  });

  it("formats JPY with 0 decimals", () => {
    assert.equal(formatMoney("1350", "JPY", 0), "¥1,350");
    assert.equal(formatMoney("1350.00", "JPY", 0), "¥1,350");
  });

  it("pads missing fraction digits to the requested decimals", () => {
    assert.equal(formatMoney("9", "USD", 2), "$9.00");
    assert.equal(formatMoney("9.5", "USD", 2), "$9.50");
  });

  it("is exact for values a float cannot hold", () => {
    // 9007199254740993 is 2^53 + 1: Number() would turn it into ...992.
    assert.equal(formatMoney("9007199254740993.01", "USD", 2), "$9,007,199,254,740,993.01");
    assert.equal(formatMoney("1234567.89", "EUR", 2), "€1,234,567.89");
  });

  it("never rounds: a fraction longer than the declared decimals is rejected", () => {
    assert.throws(() => formatMoney("9.005", "USD", 2), RangeError);
    assert.throws(() => formatMoney("1350.5", "JPY", 0), RangeError);
    // trailing zeros beyond the decimals are harmless
    assert.equal(formatMoney("1350.00", "JPY", 0), "¥1,350");
  });

  it("rejects non-decimal input instead of guessing", () => {
    for (const bad of ["", "abc", "1e3", "1,000.00", " 9.00", "-9.00", "NaN", "9."]) {
      assert.throws(() => formatMoney(bad, "USD", 2), TypeError, `input ${JSON.stringify(bad)}`);
    }
  });

  it("rejects numbers (money must stay a string end to end)", () => {
    assert.throws(() => formatMoney(9 as unknown as string, "USD", 2), TypeError);
  });

  it("rejects invalid decimals", () => {
    assert.throws(() => formatMoney("9.00", "USD", -1), RangeError);
    assert.throws(() => formatMoney("9.00", "USD", 1.5), RangeError);
  });
});

describe("lessonPriceFor / formatLessonPrice", () => {
  const prices: LessonPrice[] = [
    { currency: "USD", amount: "9.00", decimals: 2 },
    { currency: "JPY", amount: "1350", decimals: 0 },
  ];

  it("finds a currency", () => {
    assert.deepEqual(lessonPriceFor(prices, "JPY"), prices[1]);
  });

  it("returns null when the currency is not offered (no fabricated price)", () => {
    assert.equal(lessonPriceFor(prices, "EUR"), null);
  });

  it("formats from the API row", () => {
    assert.equal(formatLessonPrice(prices[0]), "$9.00");
    assert.equal(formatLessonPrice(prices[1]), "¥1,350");
  });
});

describe("credit pack helpers", () => {
  const pack: CreditPackPrice = {
    id: 3,
    code: "pack_10",
    name: "Ten",
    credits: 10,
    prices: { USD: "72.00", ZAR: "1300.00", EUR: "67.00", JPY: "10800" },
  };

  it("knows currency minor units", () => {
    assert.equal(currencyDecimals("JPY"), 0);
    assert.equal(currencyDecimals("USD"), 2);
    assert.equal(currencyDecimals("EUR"), 2);
    assert.equal(currencyDecimals("ZAR"), 2);
  });

  it("formats pack totals and exact per-lesson prices", () => {
    assert.equal(formatPackPrice(pack, "USD"), "$72.00");
    assert.equal(formatPackPrice(pack, "JPY"), "¥10,800");
    assert.equal(formatPackPerLesson(pack, "USD"), "$7.20");
    assert.equal(formatPackPerLesson(pack, "JPY"), "¥1,080");
  });

  it("omits the per-lesson figure when it would need rounding", () => {
    assert.equal(formatPackPerLesson(pack, "EUR"), "€6.70");
    assert.equal(formatPackPerLesson({ ...pack, credits: 3 }, "EUR"), null);
  });

  it("returns null for a currency the pack has no price in", () => {
    const partial = { ...pack, prices: { USD: "72.00" } } as unknown as CreditPackPrice;
    assert.equal(formatPackPrice(partial, "EUR"), null);
    assert.equal(formatPackPerLesson(partial, "EUR"), null);
  });
});

describe("dividePrice (per-lesson price of a pack)", () => {
  it("divides exactly in minor units", () => {
    assert.equal(dividePrice("72.00", 2, 10), "7.20");
    assert.equal(dividePrice("10800", 0, 10), "1080");
    assert.equal(dividePrice("9.00", 2, 1), "9.00");
  });

  it("returns null when the result is not an exact amount (never rounds)", () => {
    assert.equal(dividePrice("10.00", 2, 3), null);
    assert.equal(dividePrice("1355", 0, 10), null);
  });

  it("returns null for a non-positive or fractional count", () => {
    assert.equal(dividePrice("10.00", 2, 0), null);
    assert.equal(dividePrice("10.00", 2, -2), null);
    assert.equal(dividePrice("10.00", 2, 1.5), null);
  });
});
