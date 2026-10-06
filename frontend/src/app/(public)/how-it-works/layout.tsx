import type { Metadata } from "next";
export const metadata: Metadata = { title: "How Sharon Online Works", description: "See how live tutor matching, secure booking, and post-lesson feedback fit together.", alternates: { canonical: "/how-it-works" } };
export default function HowItWorksLayout({ children }: Readonly<{ children: React.ReactNode }>) { return children; }
