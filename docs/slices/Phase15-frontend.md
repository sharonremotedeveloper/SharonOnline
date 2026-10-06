# Phase 15 frontend slice (Package B)

Implemented locally:

- `/student/schedule` lists live student lessons in the API-provided viewer timezone, offers classroom entry only in the existing lesson window, and creates a Google Calendar template link.
- `/student/favorites` has a truthful empty state because the current backend/OpenAPI contract has no persistent favorite/bookmark endpoint. It does not invent or store a second client-only source of truth.
- Public metadata layouts cover the marketing routes, canonical URLs, OpenGraph/Twitter image references, `sitemap.ts`, `robots.ts`, and noindex metadata for student, teacher, and admin areas.

Remaining contract dependency: add a backend favorites/bookmarks API before wiring persistence and next-available-slot previews.
