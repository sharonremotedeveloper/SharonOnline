import assert from "node:assert/strict";
import test from "node:test";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

import { TutorApplicationOutcome } from "../src/components/teacher/TutorApplicationOutcome";

test("the submitted outcome renders confirmation, next steps, and a focus target instead of the wizard", () => {
  const html = renderToStaticMarkup(React.createElement(TutorApplicationOutcome, {
    outcome: {
      status: "submitted",
      title: "Application submitted successfully",
      summary: "Your application is safely in the review queue. You do not need to submit it again.",
      submittedAt: "2026-10-16T01:21:31Z",
    },
  }));

  assert.match(html, /Application submitted successfully/);
  assert.match(html, /What happens next/);
  assert.match(html, /id="application-outcome-title"/);
  assert.match(html, /tabindex="-1"/);
  assert.doesNotMatch(html, /Submit application/);
});

test("a rejected outcome uses warning styling and does not claim success", () => {
  const html = renderToStaticMarkup(React.createElement(TutorApplicationOutcome, {
    outcome: {
      status: "rejected",
      title: "A decision has been made",
      summary: "Check your notifications or email for the review decision and any available next steps.",
      submittedAt: "2026-10-16T01:21:31Z",
    },
  }));

  assert.match(html, /border-warning-border/);
  assert.doesNotMatch(html, /Application submitted successfully/);
});
