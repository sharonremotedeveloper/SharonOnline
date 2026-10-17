/**
 * Tiny, safe markdown subset for staff-written training content: headings (# to ####), "-"/"*" bullet lists and
 * paragraphs. Output is plain data rendered as React text (never HTML), so nothing in the content can inject markup.
 */
export type MdBlock =
  | { kind: "heading"; level: 2 | 3 | 4; text: string }
  | { kind: "list"; items: string[] }
  | { kind: "paragraph"; text: string };

export function parseSimpleMarkdown(body: string): MdBlock[] {
  const blocks: MdBlock[] = [];
  let para: string[] = [];
  const flush = () => {
    if (para.length) blocks.push({ kind: "paragraph", text: para.join(" ") });
    para = [];
  };
  for (const raw of body.split(/\r?\n/)) {
    const line = raw.trim();
    const heading = /^(#{1,6})\s+(.*)$/.exec(line);
    const bullet = /^[-*]\s+(.*)$/.exec(line);
    if (!line) {
      flush();
    } else if (heading) {
      flush();
      // The page title is the h1, so content headings start at h2; deeper levels collapse to h4.
      const level = Math.min(Math.max(heading[1].length + 1, 2), 4) as 2 | 3 | 4;
      blocks.push({ kind: "heading", level, text: heading[2].replace(/\s+#+\s*$/, "") });
    } else if (bullet) {
      flush();
      const last = blocks[blocks.length - 1];
      if (last?.kind === "list") last.items.push(bullet[1]);
      else blocks.push({ kind: "list", items: [bullet[1]] });
    } else {
      para.push(line);
    }
  }
  flush();
  return blocks;
}
