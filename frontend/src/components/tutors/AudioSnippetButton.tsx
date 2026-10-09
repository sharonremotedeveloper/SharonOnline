"use client";

import React, { useState, useRef, useEffect } from "react";
import { Volume2, VolumeX, Pause } from "lucide-react";

interface AudioSnippetButtonProps {
  audioUrl?: string;
  tutorName: string;
  size?: "sm" | "md";
}

export function AudioSnippetButton({ audioUrl, tutorName, size = "md" }: AudioSnippetButtonProps) {
  const [isPlaying, setIsPlaying] = useState(false);
  const [hasError, setHasError] = useState(false);
  const audioRef = useRef<HTMLAudioElement | null>(null);

  useEffect(() => {
    return () => {
      if (audioRef.current) {
        audioRef.current.pause();
        audioRef.current = null;
      }
    };
  }, []);

  if (!audioUrl || hasError) {
    if (size === "sm") {
      return (
        <button
          type="button"
          disabled
          aria-disabled="true"
          title={`Voice sample unavailable for ${tutorName}`}
          className="min-h-11 p-1.5 rounded-full bg-cream-surface text-ink-muted/50 border border-divider cursor-not-allowed flex items-center justify-center opacity-60"
        >
          <VolumeX className="w-3.5 h-3.5" />
          <span className="sr-only">Voice sample unavailable for {tutorName}</span>
        </button>
      );
    }

    return (
      <button
        type="button"
        disabled
        aria-disabled="true"
        title={`Voice sample unavailable for ${tutorName}`}
        className="min-h-11 px-3 py-1.5 rounded-xl text-sm font-medium bg-cream-surface text-ink-muted/60 border border-divider cursor-not-allowed flex items-center gap-1.5 opacity-60"
      >
        <VolumeX className="w-3.5 h-3.5 text-ink-muted/50" />
        <span>Voice sample unavailable</span>
      </button>
    );
  }

  const togglePlay = (e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();

    if (!audioRef.current) {
      audioRef.current = new Audio(audioUrl);
      audioRef.current.onended = () => setIsPlaying(false);
      audioRef.current.onerror = () => {
        setIsPlaying(false);
        setHasError(true);
      };
    }

    if (isPlaying) {
      audioRef.current.pause();
      setIsPlaying(false);
    } else {
      audioRef.current.currentTime = 0;
      audioRef.current
        .play()
        .then(() => setIsPlaying(true))
        .catch(() => {
          setIsPlaying(false);
          setHasError(true);
        });
    }
  };

  if (size === "sm") {
    return (
      <button
        type="button"
        onClick={togglePlay}
        title={isPlaying ? `Pause ${tutorName}'s voice` : `Hear ${tutorName}'s accent`}
        className={`min-h-11 p-1.5 rounded-full transition-all flex items-center justify-center ${
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
      type="button"
      onClick={togglePlay}
      className={`min-h-11 px-3 py-1.5 rounded-xl text-sm font-bold transition-all flex items-center gap-1.5 shadow-sm ${
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
