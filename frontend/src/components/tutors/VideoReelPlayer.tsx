"use client";

import React, { useState, useRef } from "react";
import { Play, Pause, Volume2, VolumeX, AlertCircle } from "lucide-react";

interface VideoReelPlayerProps {
  videoUrl?: string;
  posterUrl?: string;
  tutorName: string;
  headline?: string;
}

export function VideoReelPlayer({ videoUrl, posterUrl, tutorName, headline }: VideoReelPlayerProps) {
  const [isPlaying, setIsPlaying] = useState(false);
  const [isMuted, setIsMuted] = useState(false);
  const [hasError, setHasError] = useState(false);
  const videoRef = useRef<HTMLVideoElement | null>(null);

  if (!videoUrl || hasError) {
    return (
      <div
        role="region"
        aria-label={`${tutorName}'s video reel`}
        className="relative rounded-3xl overflow-hidden bg-cream-surface border border-divider aspect-video flex flex-col items-center justify-center p-6 text-center text-ink-muted shadow-card"
      >
        <div className="w-14 h-14 rounded-full bg-cream-deep text-ink-muted flex items-center justify-center mb-3">
          {hasError ? (
            <AlertCircle className="w-6 h-6 text-warning" />
          ) : (
            <Play className="w-6 h-6 ml-0.5 opacity-40 text-ink-muted" />
          )}
        </div>
        <div className="text-ink font-serif font-bold text-base">Video introduction unavailable</div>
        <p className="text-xs text-ink-muted mt-1 max-w-sm">
          {hasError
            ? "The video could not be loaded at this time."
            : `${tutorName} has not published a video introduction yet.`}
        </p>
        {headline && <div className="text-ink-muted/80 text-xs mt-2 italic max-w-md line-clamp-1">{headline}</div>}
      </div>
    );
  }

  const handlePlayToggle = () => {
    if (!videoRef.current) return;
    if (isPlaying) {
      videoRef.current.pause();
      setIsPlaying(false);
    } else {
      videoRef.current.play().catch(() => {
        setIsPlaying(false);
      });
      setIsPlaying(true);
    }
  };

  const handleMuteToggle = (e: React.MouseEvent) => {
    e.stopPropagation();
    if (!videoRef.current) return;
    videoRef.current.muted = !isMuted;
    setIsMuted(!isMuted);
  };

  return (
    <div className="relative rounded-3xl overflow-hidden bg-black aspect-video group shadow-card border border-divider">
      <video
        ref={videoRef}
        src={videoUrl}
        poster={posterUrl}
        playsInline
        onEnded={() => setIsPlaying(false)}
        onError={() => setHasError(true)}
        className="w-full h-full object-cover cursor-pointer"
        onClick={handlePlayToggle}
      />

      {/* Dark overlay when paused */}
      {!isPlaying && (
        <div
          onClick={handlePlayToggle}
          className="absolute inset-0 bg-black/40 backdrop-blur-[2px] flex flex-col items-center justify-center p-6 text-center cursor-pointer transition-opacity group-hover:bg-black/30"
        >
          <div className="w-16 h-16 rounded-full bg-accent text-ink flex items-center justify-center shadow-lg transition-transform group-hover:scale-110 mb-3">
            <Play className="w-7 h-7 fill-ink ml-1 text-ink" />
          </div>
          <div className="text-white font-serif font-bold text-lg">{tutorName}&apos;s 60-Second Video Reel</div>
          {headline && <div className="text-white/80 text-sm mt-1 max-w-md line-clamp-1">{headline}</div>}
        </div>
      )}

      {/* Floating control bar when playing */}
      {isPlaying && (
        <div className="absolute bottom-3 left-3 right-3 flex items-center justify-between bg-black/60 backdrop-blur-md px-4 py-2 rounded-xl text-white text-sm opacity-0 group-hover:opacity-100 transition-opacity">
          <button type="button" onClick={handlePlayToggle} className="flex items-center gap-1.5 hover:text-gold-bright font-bold">
            <Pause className="w-4 h-4 fill-white" /> Pause
          </button>

          <div className="text-sm text-white/85">60-Sec Audition Reel</div>

          <div className="flex items-center gap-2">
            <button type="button" onClick={handleMuteToggle} className="p-1 hover:text-gold-bright" aria-label={isMuted ? "Unmute" : "Mute"}>
              {isMuted ? <VolumeX className="w-4 h-4" /> : <Volume2 className="w-4 h-4" />}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
