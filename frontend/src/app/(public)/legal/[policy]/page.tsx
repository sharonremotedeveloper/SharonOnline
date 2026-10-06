import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { ShieldCheck, FileText, ArrowLeft, Calendar, Clock, ChevronRight } from "lucide-react";
import { LEGAL_POLICIES } from "@/content/legal/policies";
import { PrintButton } from "@/components/legal/PrintButton";

interface LegalPageProps {
  params: Promise<{ policy: string }>;
}

export async function generateStaticParams() {
  return Object.keys(LEGAL_POLICIES).map((policy) => ({ policy }));
}

export async function generateMetadata({ params }: LegalPageProps): Promise<Metadata> {
  const { policy: slug } = await params;
  const policy = LEGAL_POLICIES[slug];
  if (!policy) return { title: "Policy Not Found | Sharon Online" };

  return {
    title: `${policy.shortTitle} | Sharon Online Legal Hub`,
    description: policy.summary,
  };
}

interface TocItem {
  id: string;
  title: string;
  level: number;
}

function extractTableOfContents(markdown: string): TocItem[] {
  const lines = markdown.split("\n");
  const toc: TocItem[] = [];

  for (const line of lines) {
    const trimmed = line.trim();
    if (trimmed.startsWith("## ")) {
      const title = trimmed.replace(/^##\s+/, "");
      const id = title
        .toLowerCase()
        .replace(/[^a-z0-9]+/g, "-")
        .replace(/^-|-$/g, "");
      toc.push({ id, title, level: 2 });
    } else if (trimmed.startsWith("### ")) {
      const title = trimmed.replace(/^###\s+/, "");
      const id = title
        .toLowerCase()
        .replace(/[^a-z0-9]+/g, "-")
        .replace(/^-|-$/g, "");
      toc.push({ id, title, level: 3 });
    }
  }

  return toc;
}

function renderMarkdownBody(markdown: string) {
  const lines = markdown.split("\n");
  const elements: React.ReactNode[] = [];
  let currentList: string[] = [];
  let listKey = 0;

  const flushList = () => {
    if (currentList.length > 0) {
      elements.push(
        <ul key={`list-${listKey++}`} className="list-disc pl-6 space-y-2 text-ink/80 text-sm leading-relaxed my-3">
          {currentList.map((item, idx) => (
            <li key={idx} dangerouslySetInnerHTML={{ __html: formatInline(item) }} />
          ))}
        </ul>
      );
      currentList = [];
    }
  };

  const formatInline = (text: string) => {
    return text
      .replace(/\*\*(.*?)\*\*/g, "<strong class='font-bold text-ink'>$1</strong>")
      .replace(/\*(.*?)\*/g, "<em class='italic'>$1</em>")
      .replace(/`([^`]+)`/g, "<code class='bg-cream-deep px-1.5 py-0.5 rounded text-xs font-mono text-ink'>$1</code>");
  };

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i].trim();

    if (line.startsWith("- ")) {
      currentList.push(line.replace(/^- /, ""));
      continue;
    } else {
      flushList();
    }

    if (!line) continue;

    if (line.startsWith("## ")) {
      const title = line.replace(/^## /, "");
      const id = title
        .toLowerCase()
        .replace(/[^a-z0-9]+/g, "-")
        .replace(/^-|-$/g, "");
      elements.push(
        <h2
          key={`h2-${i}`}
          id={id}
          className="text-2xl font-black font-serif text-ink mt-8 mb-4 pt-6 border-t border-divider first:mt-0 first:pt-0 first:border-none scroll-mt-24"
        >
          {title}
        </h2>
      );
    } else if (line.startsWith("### ")) {
      const title = line.replace(/^### /, "");
      const id = title
        .toLowerCase()
        .replace(/[^a-z0-9]+/g, "-")
        .replace(/^-|-$/g, "");
      elements.push(
        <h3
          key={`h3-${i}`}
          id={id}
          className="text-lg font-bold font-serif text-ink mt-6 mb-2 scroll-mt-24"
        >
          {title}
        </h3>
      );
    } else if (/^\d+\.\s/.test(line)) {
      elements.push(
        <p
          key={`p-${i}`}
          className="text-sm leading-relaxed text-ink/85 font-medium my-2"
          dangerouslySetInnerHTML={{ __html: formatInline(line) }}
        />
      );
    } else {
      elements.push(
        <p
          key={`p-${i}`}
          className="text-sm leading-relaxed text-ink/80 my-3"
          dangerouslySetInnerHTML={{ __html: formatInline(line) }}
        />
      );
    }
  }

  flushList();
  return elements;
}

export default async function LegalPolicyPage({ params }: LegalPageProps) {
  const { policy: slug } = await params;
  const policy = LEGAL_POLICIES[slug];

  if (!policy) {
    notFound();
  }

  const toc = extractTableOfContents(policy.markdownContent);

  return (
    <div className="min-h-screen bg-cream-surface/30">
      {/* Top Header / Breadcrumb Bar */}
      <div className="border-b border-divider bg-white print:hidden">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-4 flex items-center justify-between">
          <div className="flex items-center gap-2 text-xs text-ink-muted">
            <Link href="/" className="hover:text-ink transition-colors">
              Home
            </Link>
            <ChevronRight className="w-3.5 h-3.5" />
            <span className="font-semibold text-ink">Legal Hub</span>
            <ChevronRight className="w-3.5 h-3.5" />
            <span className="text-cocoa font-bold">{policy.shortTitle}</span>
          </div>

          <Link
            href="/"
            className="inline-flex items-center gap-1.5 text-xs font-bold text-ink-muted hover:text-ink transition-colors"
          >
            <ArrowLeft className="w-3.5 h-3.5" />
            <span>Return to Sharon Online</span>
          </Link>
        </div>
      </div>

      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-10">
        <div className="grid grid-cols-1 lg:grid-cols-4 gap-8">
          {/* Policy Navigation Sidebar */}
          <aside className="lg:col-span-1 space-y-6 print:hidden">
            <div className="bg-white rounded-3xl p-6 border border-divider shadow-card space-y-4">
              <div className="flex items-center gap-2 pb-3 border-b border-divider text-xs font-extrabold uppercase tracking-wider text-ink-muted">
                <ShieldCheck className="w-4 h-4 text-cocoa" />
                <span>Legal & Governance</span>
              </div>

              <nav className="space-y-1">
                {Object.values(LEGAL_POLICIES).map((item) => {
                  const isActive = item.slug === policy.slug;
                  return (
                    <Link
                      key={item.slug}
                      href={`/legal/${item.slug}`}
                      className={`block px-3.5 py-2.5 rounded-xl text-xs font-bold transition-all ${
                        isActive
                          ? "bg-cocoa text-white shadow-sm"
                          : "text-ink hover:bg-cream-surface hover:text-cocoa"
                      }`}
                    >
                      {item.shortTitle}
                    </Link>
                  );
                })}
              </nav>
            </div>

            {/* Table of Contents */}
            {toc.length > 0 && (
              <div className="bg-white rounded-3xl p-6 border border-divider shadow-card space-y-3 sticky top-6">
                <div className="text-xs font-extrabold uppercase tracking-wider text-ink-muted">
                  On This Page
                </div>
                <nav className="space-y-1.5 text-xs">
                  {toc.map((item) => (
                    <a
                      key={item.id}
                      href={`#${item.id}`}
                      className={`block text-ink-muted hover:text-cocoa transition-colors leading-snug ${
                        item.level === 3 ? "pl-3 text-[11px]" : "font-semibold"
                      }`}
                    >
                      {item.title}
                    </a>
                  ))}
                </nav>
              </div>
            )}
          </aside>

          {/* Main Document Content */}
          <main className="lg:col-span-3">
            <article className="bg-white rounded-3xl p-8 sm:p-12 border border-divider shadow-card print:border-none print:shadow-none print:p-0">
              {/* Document Header */}
              <div className="space-y-4 pb-8 border-b border-divider">
                <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-cream-surface border border-divider text-xs font-bold text-cocoa">
                  <FileText className="w-3.5 h-3.5" />
                  <span>Official Policy Document</span>
                </div>

                <h1 className="text-3xl sm:text-4xl font-extrabold font-serif text-ink tracking-tight">
                  {policy.title}
                </h1>

                <p className="text-sm text-ink-muted leading-relaxed max-w-2xl">
                  {policy.summary}
                </p>

                <div className="flex flex-wrap items-center justify-between gap-4 pt-2 text-xs text-ink-muted">
                  <div className="flex items-center gap-4">
                    <span className="flex items-center gap-1.5">
                      <Calendar className="w-3.5 h-3.5 text-cocoa" />
                      <span>Last Updated: {policy.lastUpdated}</span>
                    </span>
                    <span className="flex items-center gap-1.5">
                      <Clock className="w-3.5 h-3.5 text-cocoa" />
                      <span>Standard Review: Bi-annual</span>
                    </span>
                  </div>

                  <div className="print:hidden">
                    <PrintButton />
                  </div>
                </div>
              </div>

              {/* Document Body */}
              <div className="mt-8 prose-neutral max-w-none">
                {renderMarkdownBody(policy.markdownContent)}
              </div>

              {/* Document Footer */}
              <div className="mt-12 pt-8 border-t border-divider text-xs text-ink-muted flex flex-col sm:flex-row items-center justify-between gap-4">
                <span>Sharon Online (Pty) Ltd. &bull; Registered in South Africa</span>
                <div className="flex items-center gap-2">
                  <ShieldCheck className="w-4 h-4 text-cocoa" />
                  <span>POPIA, GDPR, and APPI Certified</span>
                </div>
              </div>
            </article>
          </main>
        </div>
      </div>
    </div>
  );
}
