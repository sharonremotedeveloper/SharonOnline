import type { Metadata } from "next";
export const metadata: Metadata = { title: "Find an English Tutor | Sharon Online", description: "Browse verified tutors for focused 25-minute English lessons.", alternates: { canonical: "/tutors" } };
export default function TutorsLayout({ children }: Readonly<{ children: React.ReactNode }>) { return children; }
