import assert from "node:assert/strict";
import { test } from "node:test";
import { groupMoney, sumMoney } from "./moneyString";

test("sumMoney is exact where floats are not", () => {
  assert.equal(sumMoney(["0.10", "0.20"]), "0.30");
  assert.equal(sumMoney(["162.00", "162.00", "0.01"]), "324.01");
  assert.equal(sumMoney([]), "0.00");
  assert.equal(sumMoney(["5.00", "-7.25"]), "-2.25");
});

test("sumMoney supports zero-decimal currencies", () => {
  assert.equal(sumMoney(["1350", "1350"], 0), "2700");
});

test("groupMoney groups thousands without floats", () => {
  assert.equal(groupMoney("1234567.5"), "1,234,567.50");
  assert.equal(groupMoney("91687.50"), "91,687.50");
  assert.equal(groupMoney("12345678901234567.89"), "12,345,678,901,234,567.89");
  assert.equal(groupMoney("1350", 0), "1,350");
});

test("rejects non-money input loudly", () => {
  assert.throws(() => sumMoney(["abc"]));
});
