import type { Metadata } from "next";
export const metadata: Metadata = { title: "English Learning Materials | Sharon Online", description: "Read practical English lessons and build vocabulary for work, travel, and conversation.", alternates: { canonical: "/materials" } };
export default function MaterialsLayout({ children }: Readonly<{ children: React.ReactNode }>) { return children; }
