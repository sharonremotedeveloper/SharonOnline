# Slice T7 - teacher portal frontend (Package B)

Implemented in `feature/codex-teacher-and-seo`:

- `/teacher/profile` reads and patches the live teacher profile contract; status is displayed read-only and vetted fields are not editable.
- `/teacher/schedule` keeps the existing availability matrix and adds the live time-off POST contract with server error handling.
- `/teacher/training` and `/teacher/training/[slug]` consume the T6 overview/detail/complete endpoints and explain the calendar gate.
- Existing teacher dashboard data remains on the established live booking, wallet, and Eskom clients; no mock fallback was added.

Verification: frontend tests 203 passed, API type drift check passed, ESLint passed with zero warnings, and `next build` passed. Provider-backed behavior and authenticated browser UAT remain outside local verification.
