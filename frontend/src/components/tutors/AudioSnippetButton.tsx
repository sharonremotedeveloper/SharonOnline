"use client";

import React, { useState, useRef, useEffect } from "react";
import { Volume2, VolumeX, Pause, Play } from "lucide-react";

interface AudioSnippetButtonProps {
  audioUrl?: string;
  tutorName: string;
  size?: "sm" | "md";
}

export function AudioSnippetButton({ audioUrl, tutorName, size = "md" }: AudioSnippetButtonProps) {
  const [isPlaying, setIsPlaying] = useState(false);
  const audioRef = useRef<HTMLAudioElement | null>(null);

  const fallbackAudio =
    audioUrl ||
    "https://actions.google.com/sounds/v1/ambiences/outdoor_festival_crowd_distant.ogg"; // Clean audio fallback

  const togglePlay = (e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();

    if (!audioRef.current) {
      audioRef.current = new Audio(fallbackAudio);
      audioRef.current.onended = () => setIsPlaying(false);
      audioRef.current.onerror = () => setIsPlaying(false);
    }

    if (isPlaying) {
      audioRef.current.pause();
      setIsPlaying(false);
    } else {
      audioRef.current.currentTime = 0;
      audioRef.current
        .play()
        .then(() => setIsPlaying(true))
        .catch(() => setIsPlaying(false));
    }
  };

  useEffect(() => {
    return () => {
      if (audioRef.current) {
        audioRef.current.pause();
        audioRef.current = null;
      }
    };
  }, []);

  if (size === "sm") {
    return (
      <button
        onClick={togglePlay}
        title={isPlaying ? `Pause ${tutorName}'s voice` : `Hear ${tutorName}'s accent`}
        className={`p-1.5 rounded-full transition-all flex items-center justify-center ${
          isPlaying
            ? "bg-accent text-ink animate-pulse"
            : "bg-cream-surface hover:bg-cream-deep text-ink-muted hover:text-ink border border-divider"
        }`}
      >
        {isPlaying ? <Pause className="w-3.5 h-3.5" /> : <Volume2 className="w-3.5 h-3.5" />}
      </button>
    );
  }

  return (
    <button
      onClick={togglePlay}
      className={`px-3 py-1.5 rounded-xl text-sm font-bold transition-all flex items-center gap-1.5 shadow-sm ${
        isPlaying
          ? "bg-accent text-ink ring-2 ring-accent/40"
          : "bg-cream-surface hover:bg-cream-deep text-ink border border-divider"
      }`}
    >
      {isPlaying ? (
        <>
          <Pause className="w-3.5 h-3.5 text-ink animate-pulse" />
          <span>Playing Voice Sample...</span>
        </>
      ) : (
        <>
          <Volume2 className="w-3.5 h-3.5 text-primary" />
          <span>Hear Accent (15s)</span>
        </>
      )}
    </button>
  );
}
