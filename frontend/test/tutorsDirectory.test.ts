import assert from "node:assert/strict";
import test from "node:test";
import { buildTutorQuery, toPublicTutor } from "../src/lib/tutorsDirectory";

test("directory query maps live filters and pagination", () => {
  assert.equal(buildTutorQuery({ search: "  Maya ", accent: "ZA", specialty: "Business English", page: 2, pageSize: 12 }), "search=Maya&accent=ZA&specialty=Business+English&page=2&page_size=12");
});

test("directory adapter supplies stable card fields", () => {
  const tutor = toPublicTutor({ id: "1", full_name: "Maya Singh", specialties: ["IELTS"], rating_avg: "4.8" });
  assert.equal(tutor.full_name, "Maya Singh");
  assert.equal(tutor.rating_avg, 4.8);
  assert.deepEqual(tutor.specialties, ["IELTS"]);
});
