import type { MetadataRoute } from "next";

const SITE_URL = process.env.NEXT_PUBLIC_SITE_URL || "http://localhost:3000";

const ROUTES = [
  "/",
  "/tutors",
  "/materials",
  "/pricing",
  "/how-it-works",
  "/teach",
  "/trust-safety",
  "/support",
  "/legal/terms",
  "/legal/privacy",
  "/legal/refunds",
  "/legal/cookies",
  "/legal/child-safety",
];

// No lastModified: stamping `new Date()` told crawlers every page changed on every request.
export default function sitemap(): MetadataRoute.Sitemap {
  return ROUTES.map((route) => ({
    url: `${SITE_URL}${route}`,
    changeFrequency: route.startsWith("/legal") ? "yearly" : "weekly",
    priority: route === "/" ? 1 : route.startsWith("/legal") ? 0.3 : 0.7,
  }));
}
