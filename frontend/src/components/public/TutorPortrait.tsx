import Image from "next/image";

interface TutorPortraitProps {
  src?: string;
  name: string;
  /** Tailwind classes that size the box, e.g. "aspect-[4/5] w-full". */
  className?: string;
  sizes: string;
  priority?: boolean;
}

/** A tutor photo through next/image (resized, lazy unless `priority`), with an initials tile when there is no photo. */
export function TutorPortrait({ src, name, className = "aspect-[4/5] w-full", sizes, priority = false }: TutorPortraitProps) {
  if (!src) {
    const initials = name
      .split(" ")
      .map((p) => p[0])
      .join("")
      .slice(0, 2)
      .toUpperCase();
    return (
      <div
        role="img"
        aria-label={name}
        className={`${className} flex items-center justify-center bg-gradient-to-br from-teal to-teal-hover font-serif text-4xl font-bold text-gold-bright`}
      >
        {initials}
      </div>
    );
  }

  return (
    <div className={`${className} relative overflow-hidden bg-cream-deep`}>
      <Image src={src} alt={name} fill sizes={sizes} priority={priority} className="object-cover" />
    </div>
  );
}
