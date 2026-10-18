import assert from "node:assert/strict";
import { describe, it } from "node:test";

import {
  materialAssetType,
  moveId,
  quarantineKey,
  regateCount,
  regateWarning,
  slugify,
  trainingStatus,
  youtubeEmbedUrl,
  youtubeIdFromLink,
} from "./adminContent";
import { ApiError } from "./http";

describe("YouTube links (mirror of teachers/training.py::parse_youtube_id)", () => {
  it("reduces every accepted link shape to the id", () => {
    for (const link of [
      "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
      "https://youtube.com/watch?v=dQw4w9WgXcQ&t=42s",
      "https://m.youtube.com/watch?feature=share&v=dQw4w9WgXcQ",
      "https://youtu.be/dQw4w9WgXcQ?si=abc",
      "youtu.be/dQw4w9WgXcQ",
      "https://www.youtube.com/embed/dQw4w9WgXcQ",
      "https://www.youtube-nocookie.com/embed/dQw4w9WgXcQ",
      "https://www.youtube.com/shorts/dQw4w9WgXcQ",
      " dQw4w9WgXcQ ",
    ]) {
      assert.equal(youtubeIdFromLink(link), "dQw4w9WgXcQ", link);
    }
  });

  it("refuses other sites, look-alike hosts and broken ids", () => {
    for (const link of [
      "https://vimeo.com/123456",
      "https://www.youtube.com.evil.example/watch?v=dQw4w9WgXcQ",
      "javascript:alert(1)",
      "https://www.youtube.com/watch?v=short",
      "ftp://youtu.be/dQw4w9WgXcQ",
      "not a link",
    ]) {
      assert.equal(youtubeIdFromLink(link), null, link);
    }
  });

  it("treats an empty box as no video", () => {
    assert.equal(youtubeIdFromLink("   "), "");
  });

  it("only builds embed addresses from checked ids", () => {
    assert.equal(youtubeEmbedUrl("dQw4w9WgXcQ"), "https://www.youtube-nocookie.com/embed/dQw4w9WgXcQ?rel=0");
    assert.equal(youtubeEmbedUrl('x"><script>'), null);
    assert.equal(youtubeEmbedUrl(""), null);
  });
});

describe("re-gate confirmation", () => {
  it("reads the tutor count from the 409 answer only", () => {
    const conflict = new ApiError(409, "x", { code: "regate_confirmation_required", tutors_affected: 3 });
    assert.equal(regateCount(conflict), 3);
    assert.equal(regateCount(new ApiError(409, "x", { code: "other", tutors_affected: 3 })), null);
    assert.equal(regateCount(new ApiError(400, "x", { code: "regate_confirmation_required", tutors_affected: 3 })), null);
    assert.equal(regateCount(new Error("x")), null);
  });

  it("says what happens in plain words", () => {
    assert.match(regateWarning(1), /^1 tutor will need/);
    assert.match(regateWarning(4), /^4 tutors will need/);
    assert.match(regateWarning(4), /already booked are not affected/);
  });
});

describe("training helpers", () => {
  it("makes Django-compatible slugs", () => {
    assert.equal(slugify("  How Lessons Work!  "), "how-lessons-work");
    assert.equal(slugify("Café etiquette & tips"), "cafe-etiquette-tips");
    assert.equal(slugify("a".repeat(100)).length, 80);
    assert.equal(slugify("---"), "");
  });

  it("moves an id up or down and refuses moves off the ends", () => {
    const ids = ["a", "b", "c"];
    assert.deepEqual(moveId(ids, "b", -1), ["b", "a", "c"]);
    assert.deepEqual(moveId(ids, "b", 1), ["a", "c", "b"]);
    assert.equal(moveId(ids, "a", -1), ids);
    assert.equal(moveId(ids, "c", 1), ids);
    assert.equal(moveId(ids, "z", 1), ids);
  });

  it("labels status", () => {
    assert.equal(trainingStatus({ is_published: false, is_required: true }).label, "Draft");
    assert.equal(trainingStatus({ is_published: true, is_required: true }).tone, "live");
    assert.equal(trainingStatus({ is_published: true, is_required: false }).label, "Published · optional");
  });
});

describe("material uploads", () => {
  it("declares the type the server checks and refuses the rest before uploading", () => {
    assert.deepEqual(materialAssetType("pdf", { name: "Worksheet.PDF", size: 10, type: "" }), { contentType: "application/pdf" });
    assert.deepEqual(materialAssetType("audio", { name: "clip.mp3", size: 10, type: "" }), { contentType: "audio/mpeg" });
    assert.ok("error" in materialAssetType("pdf", { name: "clip.mp3", size: 10, type: "" }));
    assert.ok("error" in materialAssetType("audio", { name: "notes.m4a", size: 10, type: "" }));
    assert.ok("error" in materialAssetType("pdf", { name: "big.pdf", size: 26 * 1024 * 1024, type: "" }));
    assert.ok("error" in materialAssetType("pdf", { name: "empty.pdf", size: 0, type: "" }));
  });

  it("puts uploads in the admin's own quarantine folder with a safe name", () => {
    assert.equal(quarantineKey("u1", "My worksheet (final).pdf", "r"), "incoming/u1/r-My-worksheet--final-.pdf");
    assert.equal(quarantineKey("u1", "../../x.pdf", "r"), "incoming/u1/r-----x.pdf");
  });
});
