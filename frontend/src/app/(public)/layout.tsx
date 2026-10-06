import type { Metadata } from "next";

export const metadata: Metadata = {
  metadataBase: new URL(process.env.NEXT_PUBLIC_SITE_URL || "http://localhost:3000"),
  openGraph: { type: "website", siteName: "Sharon Online", images: ["/og-image.svg"] },
  twitter: { card: "summary_large_image", images: ["/og-image.svg"] },
};

export default function PublicLayout({ children }: Readonly<{ children: React.ReactNode }>) { return children; }
