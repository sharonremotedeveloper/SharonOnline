"use client";

import { useEffect, useRef, useState, useCallback } from "react";
import { Camera, Mic, Volume2, CheckCircle2, AlertTriangle, X, Play, RefreshCw, Wifi } from "lucide-react";

interface HardwareCheckModalProps {
  isOpen: boolean;
  onClose: () => void;
  onComplete?: () => void;
}

export function HardwareCheckModal({ isOpen, onClose, onComplete }: HardwareCheckModalProps) {
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const audioContextRef = useRef<AudioContext | null>(null);
  const analyserRef = useRef<AnalyserNode | null>(null);
  const animFrameRef = useRef<number | null>(null);
  const streamRef = useRef<MediaStream | null>(null);

  const [hasCamera, setHasCamera] = useState<boolean | null>(null);
  const [hasMic, setHasMic] = useState<boolean | null>(null);
  const [speakerTested, setSpeakerTested] = useState(false);
  const [micLevel, setMicLevel] = useState(0); // 0 - 100
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [pingMs, setPingMs] = useState<number | null>(null);
  const [isMeasuringPing, setIsMeasuringPing] = useState(false);

  // Stop media streams
  const stopMedia = useCallback(() => {
    if (streamRef.current) {
      streamRef.current.getTracks().forEach((track) => track.stop());
      streamRef.current = null;
    }
    if (audioContextRef.current && audioContextRef.current.state !== "closed") {
      audioContextRef.current.close().catch(() => {});
      audioContextRef.current = null;
    }
    if (animFrameRef.current) {
      cancelAnimationFrame(animFrameRef.current);
      animFrameRef.current = null;
    }
    setMicLevel(0);
  }, []);

  // Initialize media devices
  const initHardware = useCallback(async () => {
    stopMedia();
    setErrorMsg(null);
    setHasCamera(null);
    setHasMic(null);
    setIsMeasuringPing(true);
    setPingMs(null);

    // Measure real network round-trip time to server endpoint
    if (typeof window !== "undefined") {
      const pingStart = performance.now();
      fetch(`${window.location.origin}/api/proxy/auth/me`, { method: "HEAD", cache: "no-store" })
        .then(() => {
          setPingMs(Math.round(performance.now() - pingStart));
        })
        .catch(() => {
          return fetch(window.location.origin, { method: "HEAD", cache: "no-store" })
            .then(() => {
              setPingMs(Math.round(performance.now() - pingStart));
            })
            .catch(() => {
              setPingMs(null);
            });
        })
        .finally(() => {
          setIsMeasuringPing(false);
        });
    }

    try {
      if (typeof navigator === "undefined" || !navigator.mediaDevices?.getUserMedia) {
        throw new Error("WebRTC media devices not supported in this browser.");
      }

      const stream = await navigator.mediaDevices.getUserMedia({
        video: { width: { ideal: 640 }, height: { ideal: 360 } },
        audio: true,
      });

      streamRef.current = stream;

      // Camera verification
      const videoTracks = stream.getVideoTracks();
      if (videoTracks.length > 0 && videoRef.current) {
        videoRef.current.srcObject = stream;
        videoRef.current.play().catch(() => {});
        setHasCamera(true);
      } else {
        setHasCamera(false);
      }

      // Microphone volume analysis
      const audioTracks = stream.getAudioTracks();
      if (audioTracks.length > 0) {
        setHasMic(true);

        const AudioContextClass = window.AudioContext || (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext;
        if (AudioContextClass) {
          const ctx = new AudioContextClass();
          audioContextRef.current = ctx;
          const analyser = ctx.createAnalyser();
          analyser.fftSize = 64;
          analyserRef.current = analyser;

          const source = ctx.createMediaStreamSource(stream);
          source.connect(analyser);

          const dataArray = new Uint8Array(analyser.frequencyBinCount);

          const checkAudio = () => {
            if (!analyserRef.current) return;
            analyserRef.current.getByteFrequencyData(dataArray);
            let sum = 0;
            for (let i = 0; i < dataArray.length; i++) {
              sum += dataArray[i];
            }
            const avg = sum / dataArray.length;
            const normalized = Math.min(100, Math.round((avg / 128) * 100));
            setMicLevel(normalized);
            animFrameRef.current = requestAnimationFrame(checkAudio);
          };
          checkAudio();
        }
      } else {
        setHasMic(false);
      }
    } catch (err: unknown) {
      console.warn("Hardware media access warning:", err);
      const message = err instanceof Error ? err.message : "Media device permission denied.";
      setErrorMsg(message);
      // In development or sandbox environment where camera/mic are blocked or absent, allow graceful fallback
      setHasCamera(false);
      setHasMic(false);
    }
  }, [stopMedia]);

  useEffect(() => {
    if (isOpen) {
      initHardware();
    } else {
      stopMedia();
    }
    return () => {
      stopMedia();
    };
  }, [isOpen, initHardware, stopMedia]);

  // Synthetic speaker test chime using Web Audio
  const playTestChime = () => {
    try {
      const AudioCtx = window.AudioContext || (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext;
      const ctx = new AudioCtx();
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();

      osc.type = "sine";
      osc.frequency.setValueAtTime(587.33, ctx.currentTime); // D5
      osc.frequency.setValueAtTime(880.0, ctx.currentTime + 0.12); // A5

      gain.gain.setValueAtTime(0.15, ctx.currentTime);
      gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.6);

      osc.connect(gain);
      gain.connect(ctx.destination);

      osc.start();
      osc.stop(ctx.currentTime + 0.65);
      setSpeakerTested(true);
    } catch (e) {
      setSpeakerTested(true);
    }
  };

  const handleFinish = () => {
    stopMedia();
    if (onComplete) onComplete();
    onClose();
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 bg-black/70 backdrop-blur-xs flex items-center justify-center p-4">
      <div className="bg-white rounded-3xl max-w-xl w-full border border-divider shadow-2xl overflow-hidden flex flex-col max-h-[92vh]">
        {/* Header */}
        <div className="p-6 bg-cream-surface border-b border-divider flex items-center justify-between">
          <div className="space-y-1">
            <h3 className="text-xl font-black text-ink font-serif">Hardware AV Readiness Check</h3>
            <p className="text-sm text-ink-muted">Test your webcam, microphone, and speakers before entering the Zoom lesson</p>
          </div>
          <button
            onClick={() => {
              stopMedia();
              onClose();
            }}
            className="min-w-11 justify-center min-h-11 inline-flex items-center p-2 rounded-xl text-ink-muted hover:text-ink hover:bg-white transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Body */}
        <div className="p-6 space-y-6 overflow-y-auto">
          {/* Camera Preview */}
          <div className="space-y-2">
            <div className="flex items-center justify-between text-xs font-bold text-ink">
              <span className="flex items-center gap-2">
                <Camera className="w-4 h-4 text-cocoa" />
                <span>Webcam Video Feed</span>
              </span>
              {hasCamera === true ? (
                <span className="text-success flex items-center gap-1 font-bold">
                  <CheckCircle2 className="w-3.5 h-3.5" /> Working
                </span>
              ) : hasCamera === false ? (
                <span className="text-warning flex items-center gap-1 font-bold">
                  <AlertTriangle className="w-3.5 h-3.5" /> Camera Inactive
                </span>
              ) : (
                <span className="text-ink-muted animate-pulse">Requesting permission...</span>
              )}
            </div>

            <div className="relative aspect-video rounded-2xl bg-ink overflow-hidden border border-divider flex items-center justify-center">
              <video
                ref={videoRef}
                autoPlay
                playsInline
                muted
                className="w-full h-full object-cover mirror scale-x-[-1]"
              />
              {hasCamera !== true && (
                <div className="absolute inset-0 flex flex-col items-center justify-center p-4 text-center text-cream/70 bg-ink/80 space-y-2">
                  <Camera className="w-8 h-8 text-cream/75" />
                  <p className="text-sm font-medium">
                    {errorMsg ? "Camera access unavailable or blocked" : "Webcam preview active or awaiting permission"}
                  </p>
                </div>
              )}
            </div>
          </div>

          {/* Microphone Volume Meter */}
          <div className="p-4 rounded-2xl bg-cream-surface border border-divider space-y-3">
            <div className="flex items-center justify-between text-xs font-bold text-ink">
              <span className="flex items-center gap-2">
                <Mic className="w-4 h-4 text-cocoa" />
                <span>Microphone Input Level</span>
              </span>
              <span className="text-xs text-ink-muted">Speak to test bar</span>
            </div>

            <div className="flex items-center gap-1.5 h-4 bg-white p-1 rounded-lg border border-divider">
              {Array.from({ length: 16 }).map((_, i) => {
                const threshold = (i + 1) * 6.25;
                const isActive = micLevel >= threshold;
                const isHigh = i > 12;
                return (
                  <div
                    key={i}
                    className={`flex-1 h-full rounded-xs transition-all duration-75 ${
                      isActive
                        ? isHigh
                          ? "bg-accent shadow-xs"
                          : "bg-success shadow-xs"
                        : "bg-cream-deep/60"
                    }`}
                  />
                );
              })}
            </div>
          </div>

          {/* Speakers & Network Health */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <div className="p-4 rounded-2xl bg-cream-surface border border-divider flex flex-col justify-between space-y-3">
              <div className="flex items-center gap-2 text-xs font-bold text-ink">
                <Volume2 className="w-4 h-4 text-cocoa" />
                <span>Speaker Output</span>
              </div>
              <button
                type="button"
                onClick={playTestChime}
                className="min-h-11 w-full py-2 px-3 rounded-xl bg-white hover:bg-cream-deep border border-divider text-xs font-bold text-ink flex items-center justify-center gap-2 transition-colors shadow-xs"
              >
                <Play className="w-3.5 h-3.5 text-cocoa" />
                <span>{speakerTested ? "Play Sound Again" : "Play Test Chime"}</span>
              </button>
            </div>

            <div className="p-4 rounded-2xl bg-cream-surface border border-divider flex flex-col justify-between space-y-3">
              <div className="flex items-center gap-2 text-xs font-bold text-ink">
                <Wifi className="w-4 h-4 text-cocoa" />
                <span>Network Stability</span>
              </div>
              <div className="flex items-center justify-between text-xs bg-white p-2 rounded-xl border border-divider font-bold">
                <span className="text-ink">Network Latency</span>
                {isMeasuringPing ? (
                  <span className="text-ink-muted text-xs animate-pulse">Measuring...</span>
                ) : pingMs !== null ? (
                  <span className={pingMs < 100 ? "text-success" : pingMs < 250 ? "text-warning" : "text-error"}>
                    {pingMs} ms ({pingMs < 100 ? "Excellent" : pingMs < 250 ? "Good" : "High Latency"})
                  </span>
                ) : (
                  <span className="text-ink-muted text-xs">Unavailable</span>
                )}
              </div>
            </div>
          </div>
        </div>

        {/* Footer */}
        <div className="p-6 bg-cream-surface border-t border-divider flex items-center justify-between gap-3">
          <button
            type="button"
            onClick={initHardware}
            className="text-xs font-bold text-ink-muted hover:text-ink flex items-center gap-1.5 transition-colors"
          >
            <RefreshCw className="w-3.5 h-3.5" /> Re-test Devices
          </button>

          <button
            type="button"
            onClick={handleFinish}
            className="min-h-11 px-6 py-2.5 rounded-2xl bg-cocoa hover:bg-cocoa-hover text-white text-xs font-extrabold flex items-center gap-2 transition-all shadow-md"
          >
            <CheckCircle2 className="w-4 h-4" />
            <span>Ready for Lesson</span>
          </button>
        </div>
      </div>
    </div>
  );
}
