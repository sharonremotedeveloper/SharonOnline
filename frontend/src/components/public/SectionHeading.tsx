interface SectionHeadingProps {
  eyebrow?: string;
  title: string;
  description?: string;
  align?: "center" | "left";
  id?: string;
}

/** One heading pattern for every landing section: small label, one h2, one plain-English sentence. */
export function SectionHeading({ eyebrow, title, description, align = "center", id }: SectionHeadingProps) {
  return (
    <div className={align === "center" ? "mx-auto max-w-2xl text-center" : "max-w-2xl"}>
      {eyebrow && <p className="text-sm font-bold uppercase tracking-wider text-primary">{eyebrow}</p>}
      <h2 id={id} className="mt-1 font-serif text-3xl font-bold leading-tight text-ink sm:text-4xl">
        {title}
      </h2>
      {description && <p className="mt-3 text-base leading-relaxed text-ink-muted sm:text-lg">{description}</p>}
    </div>
  );
}
