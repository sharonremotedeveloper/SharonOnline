import { parseSimpleMarkdown } from "@/lib/simpleMarkdown";
import { youtubeEmbedUrl } from "@/lib/adminContent";

const HEADING_CLASS = {
  2: "mt-8 font-serif text-2xl font-bold text-ink",
  3: "mt-7 font-serif text-xl font-bold text-ink",
  4: "mt-6 font-serif text-lg font-bold text-ink",
} as const;

/** Training text: the safe Markdown subset rendered as React text (never HTML). Shared by the tutor page and the admin preview. */
export function TrainingMarkdown({ body }: { body: string }) {
  return (
    <div className="space-y-3 text-base leading-relaxed text-ink">
      {parseSimpleMarkdown(body).map((block, index) => {
        if (block.kind === "heading") {
          const Tag = `h${block.level}` as "h2" | "h3" | "h4";
          return (
            <Tag key={index} className={HEADING_CLASS[block.level]}>
              {block.text}
            </Tag>
          );
        }
        if (block.kind === "list")
          return (
            <ul key={index} className="list-disc space-y-1.5 pl-5">
              {block.items.map((item, i) => (
                <li key={i}>{item}</li>
              ))}
            </ul>
          );
        return <p key={index}>{block.text}</p>;
      })}
    </div>
  );
}

/**
 * Embedded training video (decision 2: YouTube links). Only a checked 11-character id reaches the iframe, through the
 * privacy-enhanced youtube-nocookie.com host, sandboxed to what the YouTube player needs.
 */
export function TrainingVideo({ id, title }: { id: string; title: string }) {
  const src = youtubeEmbedUrl(id);
  if (!src) return null;
  return (
    <div className="relative aspect-video w-full overflow-hidden rounded-2xl bg-ink shadow-card">
      <iframe
        src={src}
        title={`Training video: ${title}`}
        className="absolute inset-0 h-full w-full"
        loading="lazy"
        referrerPolicy="strict-origin-when-cross-origin"
        allow="accelerometer; encrypted-media; gyroscope; picture-in-picture; fullscreen"
        allowFullScreen
        sandbox="allow-scripts allow-same-origin allow-presentation allow-popups allow-popups-to-escape-sandbox"
      />
    </div>
  );
}
