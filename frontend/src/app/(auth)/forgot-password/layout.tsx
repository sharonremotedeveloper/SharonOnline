import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Reset your password | Sharon Online",
  description: "Get a link to reset your password.",
  robots: { index: false, follow: false },
};

export default function Layout({ children }: Readonly<{ children: React.ReactNode }>) {
  return children;
}
