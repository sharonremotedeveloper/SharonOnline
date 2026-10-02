/**
 * Production configuration check (Task 8.7). `instrumentation.ts` -> `boot.ts` runs this once when the server starts so a deploy with
 * missing/placeholder settings dies loudly instead of failing request by request (or worse, running on dev defaults).
 * Pure function over an env object so it is unit-tested.
 */
type Env = Record<string, string | undefined>;

const DEV_ONLY_HOSTS = ["localhost", "127.0.0.1", "0.0.0.0", "::1", "[::1]"];

function parseUrl(value: string): URL | null {
  try {
    const url = new URL(value);
    return url.protocol === "http:" || url.protocol === "https:" ? url : null;
  } catch {
    return null;
  }
}

export function serverConfigProblems(env: Env): string[] {
  const problems: string[] = [];

  if ((env.SESSION_SECRET || "").length < 32) {
    problems.push("SESSION_SECRET must be set to a random value of at least 32 characters (it signs the role/session cookie).");
  }

  const api = env.INTERNAL_API_URL || env.NEXT_PUBLIC_API_URL || "";
  if (!api) {
    problems.push("INTERNAL_API_URL (or NEXT_PUBLIC_API_URL) must point at the Django API, e.g. http://backend:8000/api/v1 - there is no safe default.");
  } else {
    const url = parseUrl(api);
    if (!url) problems.push(`INTERNAL_API_URL is not a valid http(s) URL: ${api}`);
    else if (DEV_ONLY_HOSTS.includes(url.hostname) && env.ALLOW_LOCAL_UPSTREAM !== "1") {
      problems.push("INTERNAL_API_URL points at localhost in production; set ALLOW_LOCAL_UPSTREAM=1 only for a deliberate single-host test.");
    }
  }

  const proxies = env.TRUSTED_PROXY_COUNT;
  if (proxies !== undefined && proxies !== "" && !/^\d{1,2}$/.test(proxies)) {
    problems.push("TRUSTED_PROXY_COUNT must be a small non-negative integer (number of reverse proxies in front of Next.js).");
  }

  const app = env.NEXT_PUBLIC_APP_URL;
  if (!app) {
    problems.push("NEXT_PUBLIC_APP_URL must be the public https site URL (it anchors the CSRF same-origin allow-list).");
  } else {
    const url = parseUrl(app);
    if (!url) problems.push(`NEXT_PUBLIC_APP_URL is not a valid URL: ${app}`);
    else if (url.protocol !== "https:" && env.SESSION_COOKIE_SECURE !== "false") {
      problems.push("NEXT_PUBLIC_APP_URL must be https:// (or set SESSION_COOKIE_SECURE=false for plain-http staging).");
    }
  }

  if (env.NEXT_PUBLIC_USE_MOCKS === "true") problems.push("NEXT_PUBLIC_USE_MOCKS=true is not allowed in production.");
  return problems;
}
