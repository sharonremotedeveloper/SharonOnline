import type { Metadata } from "next";
import "./globals.css";
import { Navbar } from "../components/Navbar";
import { Footer } from "../components/Footer";

export const metadata: Metadata = {
  title: "Sharon's ESL Marketplace | 25-Min 1-on-1 English Lessons",
  description:
    "Master conversational and business English with certified native and South African tutors. Fast 25-minute synchronous lessons, multi-currency checkout, and structured post-lesson feedback.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body className="min-h-screen flex flex-col bg-cream text-ink font-sans selection:bg-[#F3C995] selection:text-ink">
        <Navbar />
        <main className="flex-1">{children}</main>
        <Footer />
      </body>
    </html>
  );
}
