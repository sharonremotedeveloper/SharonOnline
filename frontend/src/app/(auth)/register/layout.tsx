import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Create your account | Sharon Online",
  description: "Create a free account to book 1-on-1 English lessons.",
  alternates: { canonical: "/register" },
};

export default function Layout({ children }: Readonly<{ children: React.ReactNode }>) {
  return children;
}
