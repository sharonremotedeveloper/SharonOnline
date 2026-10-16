import assert from "node:assert/strict";
import test from "node:test";
import { buildTutorQuery, getTutorDirectoryEmptyState, toPublicTutor } from "../src/lib/tutorsDirectory";

test("directory query maps live filters and pagination", () => {
  assert.equal(buildTutorQuery({ search: "  Maya ", accent: "ZA", specialty: "Business English", page: 2, pageSize: 12 }), "search=Maya&accent=ZA&specialty=Business+English&page=2&page_size=12");
});

test("directory query sends both visible availability and backup filters", () => {
  assert.equal(buildTutorQuery({ only_power_guard: true, only_today: true, page: 3, pageSize: 12 }), "backup_power=true&free_next_24h=true&page=3&page_size=12");
  assert.equal(buildTutorQuery({ only_power_guard: false, only_today: false, pageSize: 12 }), "page_size=12");
});

test("directory adapter supplies stable card fields", () => {
  const tutor = toPublicTutor({ id: "1", full_name: "Maya Singh", specialties: ["IELTS"], rating_avg: "4.8", has_inverter_backup: true });
  assert.equal(tutor.full_name, "Maya Singh");
  assert.equal(tutor.rating_avg, 4.8);
  assert.deepEqual(tutor.specialties, ["IELTS"]);
  assert.equal(tutor.has_inverter_backup, true);
});

test("unfiltered empty directory does not blame search filters", () => {
  assert.deepEqual(getTutorDirectoryEmptyState({ search: "", accent: "", specialty: "", learning_goal: "", only_power_guard: false, only_today: false }), {
    heading: "No tutors available yet",
    description: "We're preparing the tutor directory. Please check back soon.",
    showReset: false,
  });
});

test("filtered empty directory offers to clear filters", () => {
  assert.deepEqual(getTutorDirectoryEmptyState({ search: " Maya ", accent: "", specialty: "", learning_goal: "", only_power_guard: false, only_today: false }), {
    heading: "No tutors match these filters",
    description: "Try changing your search or removing a filter.",
    showReset: true,
  });
  assert.equal(getTutorDirectoryEmptyState({ search: "", accent: "", specialty: "", learning_goal: "", only_power_guard: false, only_today: true }).showReset, true);
});
