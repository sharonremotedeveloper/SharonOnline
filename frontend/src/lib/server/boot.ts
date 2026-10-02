import { serverConfigProblems } from "./config";

/** Node-only: validate the production config and, if it is bad, exit non-zero so the supervisor sees a failed deploy
 *  (merely throwing leaves Next serving 500s from a live process). */
export function bootCheck(env: Record<string, string | undefined> = process.env): void {
  const problems = serverConfigProblems(env);
  if (!problems.length) return;
  console.error(`\nRefusing to start: invalid production configuration.\n - ${problems.join("\n - ")}\n`);
  process.exit(1);
}
