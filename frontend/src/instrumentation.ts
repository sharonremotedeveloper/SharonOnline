/** Runs once when the Next.js server boots (not during `next build`). */
export async function register() {
  if (process.env.NEXT_RUNTIME !== "nodejs") return;
  if (process.env.NODE_ENV !== "production" || process.env.NEXT_PHASE === "phase-production-build") return;
  const { bootCheck } = await import("./lib/server/boot");
  bootCheck();
}
