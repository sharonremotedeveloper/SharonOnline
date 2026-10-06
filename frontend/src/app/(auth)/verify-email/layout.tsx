import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Verify your email | Sharon Online",
  description: "Confirm your email address.",
  robots: { index: false, follow: false },
};

export default function Layout({ children }: Readonly<{ children: React.ReactNode }>) {
  return children;
}
