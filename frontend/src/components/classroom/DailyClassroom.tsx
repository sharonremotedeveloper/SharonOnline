"use client";

import React, { useEffect, useRef, useState, useCallback } from "react";
import {
  Mic,
  MicOff,
  Video,
  VideoOff,
  Share2,
  PhoneOff,
  Settings,
  ShieldCheck,
  Loader2,
  AlertTriangle,
  User,
  Sparkles,
  Maximize2,
  Minimize2,
  ExternalLink,
  Volume2,
  X,
  Wifi,
} from "lucide-react";
import { fetchVideoSessionToken, videoSessionProblem, VideoSessionProblem } from "../../lib/videoSdk";

interface DailyClassroomProps {
  bookingId: string;
  isHost?: boolean;
  partnerName: string;
  partnerAvatar?: string;
  onLeave?: () => void;
  legacyJoinUrl?: string;
}

export function DailyClassroom({
  bookingId,
  isHost = false,
  partnerName,
  partnerAvatar,
  onLeave,
  legacyJoinUrl,
}: DailyClassroomProps) {
  const [joined, setJoined] = useState(false);
  const [connecting, setConnecting] = useState(false);
  const [problem, setProblem] = useState<VideoSessionProblem | null>(null);

  const [remoteUserJoined, setRemoteUserJoined] = useState(false);
  const [networkQuality, setNetworkQuality] = useState<"good" | "low" | "reconnecting">("good");

  const containerRef = useRef<HTMLDivElement | null>(null);
  const callFrameRef = useRef<any>(null);

  const finishLeave = useCallback(() => {
    callFrameRef.current = null;
    setJoined(false);
    setConnecting(false);
    setRemoteUserJoined(false);
    onLeave?.();
  }, [onLeave]);

  // Clean up Daily call frame on unmount
  useEffect(() => {
    return () => {
      if (callFrameRef.current) {
        try {
          callFrameRef.current.destroy();
        } catch (e) {
          console.warn("Error destroying Daily frame:", e);
        }
        callFrameRef.current = null;
      }
    };
  }, []);

  const handleLeave = useCallback(async () => {
    if (callFrameRef.current) {
      try {
        await callFrameRef.current.leave();
        callFrameRef.current.destroy();
      } catch (e) {
        console.warn("Error leaving Daily call:", e);
      }
    }
    finishLeave();
  }, [finishLeave]);

  const joinSession = useCallback(async () => {
    setConnecting(true);
    setProblem(null);

    try {
      const data = await fetchVideoSessionToken(bookingId);

      // Only attempt browser WebRTC initialization if window is defined
      if (typeof window === "undefined" || !containerRef.current) {
        setJoined(true);
        setConnecting(false);
        return;
      }

      // Dynamic import of daily-js to guarantee zero SSR side effects
      const DailyModule = await import("@daily-co/daily-js");
      const DailyIframe = DailyModule.default || DailyModule;

      if (callFrameRef.current) {
        try {
          callFrameRef.current.destroy();
        } catch {
          /* ignore */
        }
        callFrameRef.current = null;
      }

      const roomUrl = data.room_url || `https://api.daily.co/${data.session_name}`;

      const callFrame = DailyIframe.createFrame(containerRef.current, {
        iframeStyle: {
          width: "100%",
          height: "100%",
          minHeight: "540px",
          border: "0",
          borderRadius: "1rem",
        },
        showLeaveButton: true,
        showFullscreenButton: true,
        theme: {
          colors: {
            accent: "#4A3525", // Cocoa
            accentText: "#FFFFFF",
            background: "#FAF7F2", // Cream
            backgroundAccent: "#F2EBE1", // Cream surface
            baseText: "#1F1B16", // Ink
            border: "#E5DDD0", // Divider
            mainAreaBg: "#1F1B16",
          },
        },
      });

      callFrameRef.current = callFrame;

      callFrame.on("joined-meeting", () => {
        setJoined(true);
        setConnecting(false);
      });

      callFrame.on("participant-joined", (event: any) => {
        if (!event?.participant?.local) {
          setRemoteUserJoined(true);
        }
      });

      callFrame.on("participant-left", (event: any) => {
        if (!event?.participant?.local) {
          const participants = callFrame.participants?.() || {};
          const remoteCount = Object.values(participants).filter((p: any) => !p?.local).length;
          setRemoteUserJoined(remoteCount > 0);
        }
      });

      callFrame.on("network-connection", (event: any) => {
        if (event?.event === "interrupted" || event?.event === "connected-poor") {
          setNetworkQuality("low");
        } else {
          setNetworkQuality("good");
        }
      });

      callFrame.on("left-meeting", () => {
        // Daily has already completed leave(); calling leave() again here can
        // race the iframe teardown and produce an avoidable SDK error.
        try {
          callFrame.destroy();
        } catch {
          /* ignore teardown errors after the SDK left */
        }
        finishLeave();
      });

      callFrame.on("error", (event: any) => {
        console.error("Daily call error:", event);
        setProblem({
          kind: "other",
          message: event?.errorMsg || "A video connection error occurred. Please try again.",
        });
        setConnecting(false);
      });

      await callFrame.join({
        url: roomUrl,
        token: data.token,
        userName: data.user_name,
      });
    } catch (err) {
      console.error("Failed to join video session:", err);
      setProblem(videoSessionProblem(err));
      setConnecting(false);
      setJoined(false);
    }
  }, [bookingId, finishLeave]);

  return (
    <div className="space-y-4">
      {/* Problem Alert Banner */}
      {problem && (
        <div
          role="alert"
          className="p-4 rounded-2xl bg-amber-50 border border-amber-200 text-amber-900 flex items-start gap-3 shadow-xs"
        >
          <AlertTriangle className="w-5 h-5 text-amber-600 shrink-0 mt-0.5" />
          <div className="flex-1 text-sm space-y-1">
            <p className="font-bold">Classroom Notice</p>
            <p>{problem.message}</p>
          </div>
          <button
            type="button"
            onClick={() => setProblem(null)}
            className="text-amber-700 hover:text-amber-900 p-1 rounded-lg"
          >
            <X className="w-4 h-4" />
          </button>
        </div>
      )}

      {/* In-Meeting Live Video Frame */}
      <div
        className={`relative w-full rounded-3xl overflow-hidden bg-neutral-900 border border-divider shadow-card ${
          joined ? "block" : "hidden"
        }`}
      >
        {/* Floating Top Status Bar */}
        <div className="absolute top-3 left-3 right-3 z-10 flex items-center justify-between pointer-events-none">
          <div className="flex items-center gap-2 pointer-events-auto bg-neutral-900/80 backdrop-blur-md px-3 py-1.5 rounded-full border border-neutral-700 text-white text-xs font-semibold shadow-md">
            <span
              className={`w-2 h-2 rounded-full ${
                remoteUserJoined ? "bg-emerald-400 animate-pulse" : "bg-amber-400"
              }`}
            />
            <span>
              {remoteUserJoined ? `${partnerName} in classroom` : `Waiting for ${partnerName}...`}
            </span>
          </div>

          <div className="flex items-center gap-2 pointer-events-auto">
            {networkQuality === "low" && (
              <span className="flex items-center gap-1 bg-amber-900/80 backdrop-blur-md px-2.5 py-1 rounded-full border border-amber-600 text-amber-200 text-xs font-semibold">
                <Wifi className="w-3 h-3 animate-pulse" /> Low Bandwidth
              </span>
            )}
            <button
              type="button"
              onClick={handleLeave}
              className="min-h-9 px-3 py-1 rounded-full bg-red-600/90 hover:bg-red-700 text-white text-xs font-bold transition-colors flex items-center gap-1.5 shadow-md"
            >
              <PhoneOff className="w-3.5 h-3.5" /> Leave Lesson
            </button>
          </div>
        </div>

        {/* Daily Container Frame */}
        <div
          ref={containerRef}
          className="w-full min-h-[500px] sm:min-h-[560px] lg:min-h-[600px] bg-neutral-950"
        />
      </div>

      {/* Pre-Join Cockpit Staging Card */}
      {!joined && (
        <div className="rounded-3xl bg-white border border-divider shadow-card p-6 sm:p-8 space-y-6">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-divider pb-5">
            <div className="space-y-1">
              <span className="text-xs font-mono font-bold uppercase tracking-wider text-cocoa bg-cocoa/10 px-2.5 py-0.5 rounded-full inline-flex items-center gap-1.5">
                <ShieldCheck className="w-3.5 h-3.5" /> Live Synchronous Classroom
              </span>
              <h2 className="text-lg sm:text-xl font-black text-ink font-serif">
                In-Browser Classroom Stage
              </h2>
              <p className="text-xs sm:text-sm text-ink-muted">
                High-definition WebRTC video powered by Daily.co with synchronized learning pad.
              </p>
            </div>

            {/* Partner Indicator */}
            <div className="flex items-center gap-3 bg-cream-surface px-4 py-2.5 rounded-2xl border border-divider">
              <div className="w-10 h-10 rounded-xl bg-cocoa/10 text-cocoa flex items-center justify-center font-bold text-sm shrink-0 overflow-hidden">
                {partnerAvatar ? (
                  <img src={partnerAvatar} alt={partnerName} className="w-full h-full object-cover" />
                ) : (
                  <User className="w-5 h-5" />
                )}
              </div>
              <div className="text-left">
                <span className="text-xs text-ink-muted block">Partner</span>
                <span className="text-sm font-bold text-ink truncate block max-w-[140px]">
                  {partnerName}
                </span>
              </div>
            </div>
          </div>

          {/* Action Row */}
          <div className="flex flex-col sm:flex-row items-stretch sm:items-center gap-3">
            <button
              type="button"
              disabled={connecting}
              onClick={joinSession}
              className={`min-h-12 px-6 py-3 rounded-2xl font-black text-sm transition-all flex items-center justify-center gap-2 shadow-sm ${
                connecting
                  ? "bg-cocoa/60 text-white cursor-wait"
                  : isHost
                  ? "bg-cocoa text-white hover:bg-cocoa-hover shadow-cocoa/20 hover:scale-[1.01]"
                  : "bg-terracotta text-white hover:bg-terracotta-hover shadow-terracotta/20 hover:scale-[1.01]"
              }`}
            >
              {connecting ? (
                <>
                  <Loader2 className="w-4 h-4 animate-spin" />
                  <span>Connecting to Live Stage...</span>
                </>
              ) : isHost ? (
                <>
                  <Video className="w-4 h-4" />
                  <span>Open Classroom as Host</span>
                </>
              ) : (
                <>
                  <Video className="w-4 h-4" />
                  <span>Enter Classroom</span>
                </>
              )}
            </button>

            {/* Quick AV Readiness Notice */}
            <div className="flex items-center gap-2 px-3 py-2 text-xs text-ink-muted bg-cream-surface rounded-xl border border-divider">
              <Sparkles className="w-3.5 h-3.5 text-cocoa" />
              <span>Camera &amp; mic permissions will be requested upon entry.</span>
            </div>

            {/* Optional Legacy Zoom App Fallback */}
            {legacyJoinUrl && (
              <a
                href={legacyJoinUrl}
                target="_blank"
                rel="noopener noreferrer"
                className="min-h-12 px-4 py-3 rounded-2xl border border-divider hover:bg-cream-surface text-ink-muted hover:text-ink text-xs font-bold transition-all flex items-center justify-center gap-1.5"
              >
                <ExternalLink className="w-3.5 h-3.5" />
                <span>Launch in Zoom App</span>
              </a>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
