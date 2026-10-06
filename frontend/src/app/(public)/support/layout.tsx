import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Help and FAQ | Sharon Online",
  description: "Answers about lessons, payments, refunds and your account.",
  alternates: { canonical: "/support" },
};

export default function Layout({ children }: Readonly<{ children: React.ReactNode }>) {
  return children;
}
