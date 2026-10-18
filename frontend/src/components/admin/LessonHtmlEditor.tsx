"use client";

import { useEffect, useRef, useState } from "react";
import { Bold, Code2, Heading, Italic, Link2, List, ListOrdered, Pilcrow, Unlink } from "lucide-react";

/**
 * A small WYSIWYG editor for lesson HTML (Wave 2). It writes plain formatting only (headings, paragraphs, bold, italic,
 * lists, links); the server cleans whatever arrives (materials/sanitize.py), so this is a convenience, not the defence.
 * Pasted text arrives as plain text so formatting from Word or web pages does not come along. "HTML" shows the source for
 * the rare edit the toolbar cannot do (tables).
 *
 * document.execCommand is deprecated but supported by every current browser and is still the only built-in way to edit
 * rich text without a library.
 */
type Tool = { label: string; icon: typeof Bold; command: string; arg?: string };

const TOOLS: Tool[] = [
  { label: "Heading", icon: Heading, command: "formatBlock", arg: "h3" },
  { label: "Paragraph", icon: Pilcrow, command: "formatBlock", arg: "p" },
  { label: "Bold", icon: Bold, command: "bold" },
  { label: "Italic", icon: Italic, command: "italic" },
  { label: "Bulleted list", icon: List, command: "insertUnorderedList" },
  { label: "Numbered list", icon: ListOrdered, command: "insertOrderedList" },
  { label: "Add link", icon: Link2, command: "createLink" },
  { label: "Remove link", icon: Unlink, command: "unlink" },
];

export function LessonHtmlEditor({ id, value, onChange, labelledBy }: { id: string; value: string; onChange: (html: string) => void; labelledBy: string }) {
  const surface = useRef<HTMLDivElement>(null);
  const [source, setSource] = useState(false);

  // Uncontrolled surface: write the HTML in once (and when coming back from source view), never on every keystroke,
  // or the caret would jump to the start.
  useEffect(() => {
    if (!source && surface.current && surface.current.innerHTML !== value) surface.current.innerHTML = value;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [source]);

  const run = (command: string, arg?: string) => {
    surface.current?.focus();
    document.execCommand("defaultParagraphSeparator", false, "p");
    document.execCommand(command, false, arg);
    if (surface.current) onChange(surface.current.innerHTML);
  };

  const apply = (tool: Tool) => {
    if (tool.command !== "createLink") return run(tool.command, tool.arg);
    const url = window.prompt("Link address (https://…)", "https://");
    if (!url) return;
    if (!/^(https?:\/\/|mailto:)/i.test(url.trim())) {
      window.alert("Links must start with https://, http:// or mailto:");
      return;
    }
    run("createLink", url.trim());
  };

  return (
    <div className="overflow-hidden rounded-2xl border border-divider bg-white focus-within:border-cocoa focus-within:ring-2 focus-within:ring-cocoa/30">
      <div role="toolbar" aria-label="Formatting" className="flex flex-wrap items-center gap-0.5 border-b border-divider bg-cream-surface p-1">
        {TOOLS.map((tool) => {
          const Icon = tool.icon;
          return (
            <button
              key={tool.label}
              type="button"
              title={tool.label}
              aria-label={tool.label}
              disabled={source}
              onMouseDown={(e) => e.preventDefault()}
              onClick={() => apply(tool)}
              className="min-h-11 min-w-11 inline-flex items-center justify-center rounded-lg text-ink hover:bg-white disabled:opacity-30"
            >
              <Icon className="h-4 w-4" aria-hidden="true" />
            </button>
          );
        })}
        <button
          type="button"
          aria-pressed={source}
          onClick={() => setSource((s) => !s)}
          className={`min-h-11 ml-auto inline-flex items-center gap-1.5 rounded-lg px-3 text-xs font-bold ${source ? "bg-cocoa text-white" : "text-ink-muted hover:bg-white hover:text-ink"}`}
        >
          <Code2 className="h-4 w-4" aria-hidden="true" /> HTML
        </button>
      </div>
      {source ? (
        <textarea
          id={id}
          aria-labelledby={labelledBy}
          rows={16}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          className="block w-full resize-y border-0 p-4 font-mono text-sm leading-relaxed text-ink focus:outline-none"
        />
      ) : (
        <div
          id={id}
          ref={surface}
          role="textbox"
          aria-multiline="true"
          aria-labelledby={labelledBy}
          contentEditable
          suppressContentEditableWarning
          onInput={(e) => onChange((e.target as HTMLDivElement).innerHTML)}
          onPaste={(e) => {
            e.preventDefault();
            document.execCommand("insertText", false, e.clipboardData.getData("text/plain"));
          }}
          className="lesson-html min-h-[16rem] p-4 font-serif text-base text-ink focus:outline-none sm:p-5"
        />
      )}
    </div>
  );
}
