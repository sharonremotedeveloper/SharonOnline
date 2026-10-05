import assert from "node:assert/strict";
import test from "node:test";

import { ApiError } from "./http";
import {
  TIME_BLOCKS,
  conflictsFromError,
  matrixToRows,
  rowsToMatrix,
  wouldChangeSavedWindows,
  type AvailabilityRow,
  type WeeklyMatrix,
} from "./availability";

const closed = () => new Array(TIME_BLOCKS.length).fill(false) as boolean[];
const open = (...indexes: number[]) => closed().map((_, i) => indexes.includes(i));

test("consecutive blocks merge into one window and the lunch gap splits windows", () => {
  const matrix: WeeklyMatrix = { 0: open(0, 1, 2, 3, 4, 5) };
  assert.deepEqual(matrixToRows(matrix), [
    { day_of_week: 0, start_time: "08:00", end_time: "12:00" },
    { day_of_week: 0, start_time: "13:00", end_time: "15:00" },
  ]);
});

test("a closed grid sends an empty matrix and days without blocks send nothing", () => {
  assert.deepEqual(matrixToRows({}), []);
  assert.deepEqual(matrixToRows({ 2: closed() }), []);
});

test("windows are kept per day and in order", () => {
  const rows = matrixToRows({ 4: open(1), 1: open(0, 1) });
  assert.deepEqual(rows, [
    { day_of_week: 1, start_time: "08:00", end_time: "10:00" },
    { day_of_week: 4, start_time: "09:00", end_time: "10:00" },
  ]);
});

test("rowsToMatrix opens only fully covered blocks of active rows", () => {
  const rows: AvailabilityRow[] = [
    { day_of_week: 0, start_time: "09:00:00", end_time: "11:00:00", is_active: true },
    { day_of_week: 1, start_time: "09:00:00", end_time: "10:30:00", is_active: true },
    { day_of_week: 2, start_time: "09:00:00", end_time: "10:00:00", is_active: false },
  ];
  const matrix = rowsToMatrix(rows);
  assert.deepEqual(matrix[0], open(1, 2));
  assert.deepEqual(matrix[1], open(1));
  assert.deepEqual(matrix[2], closed());
});

test("round trip: grid -> windows -> grid is stable", () => {
  const matrix: WeeklyMatrix = { 0: open(0, 1, 2), 3: open(5, 6, 7, 8) };
  const rows = matrixToRows(matrix).map((r) => ({ ...r, is_active: true }));
  const back = rowsToMatrix(rows);
  assert.deepEqual(back[0], matrix[0]);
  assert.deepEqual(back[3], matrix[3]);
  assert.equal(wouldChangeSavedWindows(rows), false);
});

test("off-grid or overlapping saved windows are detected before they are overwritten", () => {
  assert.equal(wouldChangeSavedWindows([{ day_of_week: 0, start_time: "09:30:00", end_time: "12:00:00", is_active: true }]), true);
  assert.equal(
    wouldChangeSavedWindows([
      { day_of_week: 0, start_time: "09:00:00", end_time: "12:00:00", is_active: true },
      { day_of_week: 0, start_time: "11:00:00", end_time: "13:00:00", is_active: true },
    ]),
    true
  );
  assert.equal(wouldChangeSavedWindows([]), false);
});

test("conflictsFromError reads the 409 contract and ignores everything else", () => {
  const conflicts = [{ booking_id: "b1", start_time_utc: "2026-01-05T08:00:00+00:00", end_time_utc: "2026-01-05T08:25:00+00:00" }];
  assert.deepEqual(conflictsFromError(new ApiError(409, "x", { code: "availability_conflicts", conflicts })), conflicts);
  assert.equal(conflictsFromError(new ApiError(409, "x", { code: "other" })), null);
  assert.equal(conflictsFromError(new ApiError(400, "x", { code: "availability_conflicts", conflicts })), null);
  assert.equal(conflictsFromError(new Error("boom")), null);
});
