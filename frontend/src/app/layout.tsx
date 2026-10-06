import type { Metadata, Viewport } from "next";
import { DM_Sans, Lora } from "next/font/google";
import "./globals.css";
import { Navbar } from "../components/Navbar";
import { Footer } from "../components/Footer";
import { AuthProvider } from "@/context/AuthContext";
import { VerifyEmailBanner } from "@/components/account/VerifyEmailBanner";
import { CookieBanner } from "@/components/legal/CookieBanner";

// Self-hosted by next/font: no render-blocking @import and no visitor IP sent to Google (GDPR).
const dmSans = DM_Sans({ subsets: ["latin"], variable: "--font-dm-sans", display: "swap" });
const lora = Lora({ subsets: ["latin"], variable: "--font-lora", display: "swap" });

const TITLE = "Sharon Online | 1-on-1 English Lessons with Friendly South African Tutors";
const DESCRIPTION =
  "Speak English with confidence. Private 25-minute video lessons with certified, friendly South African tutors. Pick a time in your own time zone. First lesson refundable.";

export const metadata: Metadata = {
  metadataBase: new URL(process.env.NEXT_PUBLIC_SITE_URL || "http://localhost:3000"),
  title: { default: TITLE, template: "%s | Sharon Online" },
  description: DESCRIPTION,
  applicationName: "Sharon Online",
  alternates: { canonical: "/" },
  openGraph: { type: "website", siteName: "Sharon Online", title: TITLE, description: DESCRIPTION },
  twitter: { card: "summary_large_image", title: TITLE, description: DESCRIPTION },
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  themeColor: "#0D4440",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className={`${dmSans.variable} ${lora.variable}`}>
      <body className="min-h-screen flex flex-col bg-cream text-ink font-sans selection:bg-[#F3C995] selection:text-ink">
        <a
          href="#main"
          className="sr-only focus:not-sr-only focus:fixed focus:left-4 focus:top-4 focus:z-[100] focus:rounded-xl focus:bg-white focus:px-4 focus:py-3 focus:text-sm focus:font-bold focus:text-ink focus:shadow-lg"
        >
          Skip to main content
        </a>
        <AuthProvider>
          <Navbar />
          <VerifyEmailBanner />
          <main id="main" tabIndex={-1} className="flex-1 focus:outline-none">
            {children}
          </main>
          <Footer />
          <CookieBanner />
        </AuthProvider>
      </body>
    </html>
  );
}
