import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { isCompactFooterArea, isTabActive, signedInAuthRedirect, tabsFor } from "./appTabs";

describe("mobile app chrome rules", () => {
  it("uses the compact footer only in signed-in areas and account pages", () => {
    for (const p of ["/student/dashboard", "/teacher", "/admin/disputes", "/login", "/register", "/verify-email"]) {
      assert.equal(isCompactFooterArea(p), true, p);
    }
    for (const p of ["/", "/tutors", "/pricing", "/legal/terms", "/students-guide", "/teach"]) {
      assert.equal(isCompactFooterArea(p), false, p);
    }
  });

  it("gives students and tutors at most 5 tabs and nobody else any", () => {
    assert.equal(tabsFor("/student/dashboard", "student").length, 5);
    assert.equal(tabsFor("/tutors", "student").length, 5);
    assert.equal(tabsFor("/teacher/schedule", "teacher").length, 5);
    assert.deepEqual(tabsFor("/tutors", null), []);
    assert.deepEqual(tabsFor("/admin/dashboard", "admin"), []);
    assert.deepEqual(tabsFor("/student/dashboard", "teacher"), []);
  });

  it("hides tabs in the live classroom and on the tutor application", () => {
    assert.deepEqual(tabsFor("/student/classroom/abc", "student"), []);
    assert.deepEqual(tabsFor("/teacher/classroom/abc", "teacher"), []);
    assert.deepEqual(tabsFor("/teacher/apply", "teacher"), []);
  });

  it("marks the right tab active, including related pages", () => {
    const tabs = tabsFor("/student/history", "student");
    const active = tabs.filter((t) => isTabActive(t, "/student/history")).map((t) => t.label);
    assert.deepEqual(active, ["Lessons"]);
    assert.deepEqual(tabs.filter((t) => isTabActive(t, "/student/book/x")).map((t) => t.label), ["Book"]);
  });

  it("sends signed-in users away from sign-in and register only", () => {
    assert.equal(signedInAuthRedirect("/login", "student"), "/student/dashboard");
    assert.equal(signedInAuthRedirect("/register", "teacher"), "/teacher/dashboard");
    assert.equal(signedInAuthRedirect("/login", "admin"), "/admin/dashboard");
    assert.equal(signedInAuthRedirect("/login", null), null);
    assert.equal(signedInAuthRedirect("/reset-password", "student"), null);
    assert.equal(signedInAuthRedirect("/verify-email", "student"), null);
  });
});
