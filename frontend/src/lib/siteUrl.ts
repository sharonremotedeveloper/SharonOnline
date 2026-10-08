/**
 * Public origin of this site, used for canonical URLs, Open Graph, sitemap and robots.
 * Order: explicit site URL, the app URL that already anchors the CSRF allow-list,
 * the Vercel production domain, the Vercel deployment host, then localhost for local dev only.
 */
type Env = Record<string, string | undefined>;

function asOrigin(value: string | undefined): string | null {
  const v = value?.trim();
  if (!v) return null;
  const withScheme = /^https?:\/\//i.test(v) ? v : `https://${v}`;
  try {
    return new URL(withScheme).origin;
  } catch {
    return null;
  }
}

export function resolveSiteUrl(env: Env = process.env): string {
  return (
    asOrigin(env.NEXT_PUBLIC_SITE_URL) ??
    asOrigin(env.NEXT_PUBLIC_APP_URL) ??
    asOrigin(env.VERCEL_PROJECT_PRODUCTION_URL) ??
    asOrigin(env.VERCEL_URL) ??
    "http://localhost:3000"
  );
}

export const SITE_URL = resolveSiteUrl();
