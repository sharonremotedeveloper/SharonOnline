import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Choose a new password | Sharon Online",
  description: "Choose a new password for your account.",
  robots: { index: false, follow: false },
};

export default function Layout({ children }: Readonly<{ children: React.ReactNode }>) {
  return children;
}
