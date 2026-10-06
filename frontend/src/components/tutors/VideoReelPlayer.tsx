"use client";

import React, { useState, useRef } from "react";
import { Play, Pause, Volume2, VolumeX, Maximize2 } from "lucide-react";

interface VideoReelPlayerProps {
  videoUrl?: string;
  posterUrl?: string;
  tutorName: string;
  headline?: string;
}

export function VideoReelPlayer({ videoUrl, posterUrl, tutorName, headline }: VideoReelPlayerProps) {
  const [isPlaying, setIsPlaying] = useState(false);
  const [isMuted, setIsMuted] = useState(false);
  const videoRef = useRef<HTMLVideoElement | null>(null);

  const fallbackVideo =
    videoUrl ||
    "https://assets.mixkit.co/videos/preview/mixkit-woman-talking-on-video-call-41292-large.mp4";

  const handlePlayToggle = () => {
    if (!videoRef.current) return;
    if (isPlaying) {
      videoRef.current.pause();
      setIsPlaying(false);
    } else {
      videoRef.current.play();
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
        src={fallbackVideo}
        poster={posterUrl}
        playsInline
        onEnded={() => setIsPlaying(false)}
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
          <div className="text-white font-serif font-bold text-lg">{tutorName}'s 60-Second Video Reel</div>
          {headline && <div className="text-white/80 text-sm mt-1 max-w-md line-clamp-1">{headline}</div>}
        </div>
      )}

      {/* Floating control bar when playing */}
      {isPlaying && (
        <div className="absolute bottom-3 left-3 right-3 flex items-center justify-between bg-black/60 backdrop-blur-md px-4 py-2 rounded-xl text-white text-sm opacity-0 group-hover:opacity-100 transition-opacity">
          <button onClick={handlePlayToggle} className="flex items-center gap-1.5 hover:text-gold-bright font-bold">
            <Pause className="w-4 h-4 fill-white" /> Pause
          </button>

          <div className="text-sm text-white/85">60-Sec Audition Reel</div>

          <div className="flex items-center gap-2">
            <button onClick={handleMuteToggle} className="p-1 hover:text-gold-bright">
              {isMuted ? <VolumeX className="w-4 h-4" /> : <Volume2 className="w-4 h-4" />}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
