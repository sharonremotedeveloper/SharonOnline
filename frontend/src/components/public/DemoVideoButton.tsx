"use client";

import { useState } from "react";
import { Play } from "lucide-react";
import { Modal } from "@/components/ui/Modal";

/** Only rendered when a real demo video URL is configured (NEXT_PUBLIC_DEMO_VIDEO_URL); never a placeholder. */
export function DemoVideoButton({ src }: { src: string }) {
  const [open, setOpen] = useState(false);

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="inline-flex min-h-[52px] w-full items-center justify-center gap-2 rounded-xl border border-white/30 bg-white/10 px-6 text-base font-bold text-white transition-colors hover:bg-white/20 sm:w-auto"
      >
        <Play className="h-4 w-4 fill-gold-bright text-gold-bright" aria-hidden="true" /> Watch a sample lesson
      </button>
      <Modal isOpen={open} onClose={() => setOpen(false)} title="A Sharon Online lesson">
        <div className="aspect-video overflow-hidden rounded-xl bg-black">
          <iframe
            src={src}
            title="Sharon Online sample lesson"
            className="h-full w-full border-0"
            allow="autoplay; encrypted-media; picture-in-picture"
            allowFullScreen
          />
        </div>
      </Modal>
    </>
  );
}
