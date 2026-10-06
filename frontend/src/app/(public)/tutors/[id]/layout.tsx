import type { Metadata } from "next";
export async function generateMetadata({ params }: { params: Promise<{ id: string }> }): Promise<Metadata> { const { id } = await params; return { title: `English Tutor ${id} | Sharon Online`, description: "View tutor experience, specialties, and live lesson availability.", alternates: { canonical: `/tutors/${id}` } }; }
export default function TutorLayout({ children }: Readonly<{ children: React.ReactNode }>) { return children; }
