import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Sign in | Sharon Online",
  description: "Sign in to book and join your English lessons.",
  robots: { index: false, follow: false },
};

export default function Layout({ children }: Readonly<{ children: React.ReactNode }>) {
  return children;
}
