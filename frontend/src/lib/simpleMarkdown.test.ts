import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { parseSimpleMarkdown } from "./simpleMarkdown";

describe("training markdown", () => {
  it("renders ### headings as headings, not text (production bug 2026-10-17)", () => {
    const blocks = parseSimpleMarkdown("### The lesson\nEvery lesson is 25 minutes.");
    assert.deepEqual(blocks, [
      { kind: "heading", level: 4, text: "The lesson" },
      { kind: "paragraph", text: "Every lesson is 25 minutes." },
    ]);
  });

  it("maps # and ## below the page title", () => {
    assert.deepEqual(parseSimpleMarkdown("# A\n## B").map((b) => b.kind === "heading" && b.level), [2, 3]);
  });

  it("groups consecutive bullets into one list and joins wrapped paragraph lines", () => {
    const blocks = parseSimpleMarkdown("- one\n* two\n\nline a\nline b\n- three");
    assert.deepEqual(blocks, [
      { kind: "list", items: ["one", "two"] },
      { kind: "paragraph", text: "line a line b" },
      { kind: "list", items: ["three"] },
    ]);
  });

  it("keeps markup characters as plain text", () => {
    const [block] = parseSimpleMarkdown("<script>alert(1)</script>");
    assert.deepEqual(block, { kind: "paragraph", text: "<script>alert(1)</script>" });
  });
});
