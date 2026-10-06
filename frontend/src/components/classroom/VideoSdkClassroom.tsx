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
} from "lucide-react";
import { fetchVideoSessionToken, videoSessionProblem, VideoSessionProblem } from "../../lib/videoSdk";

interface VideoSdkClassroomProps {
  bookingId: string;
  isHost?: boolean;
  partnerName: string;
  partnerAvatar?: string;
  onLeave?: () => void;
  legacyJoinUrl?: string;
}

export function VideoSdkClassroom({
  bookingId,
  isHost = false,
  partnerName,
  partnerAvatar,
  onLeave,
  legacyJoinUrl,
}: VideoSdkClassroomProps) {
  const [joined, setJoined] = useState(false);
  const [connecting, setConnecting] = useState(false);
  const [problem, setProblem] = useState<VideoSessionProblem | null>(null);

  const [isAudioMuted, setIsAudioMuted] = useState(false);
  const [isVideoOff, setIsVideoOff] = useState(false);
  const [isSharing, setIsSharing] = useState(false);
  const [remoteUserJoined, setRemoteUserJoined] = useState(false);
  const [remoteUserName, setRemoteUserName] = useState<string>(partnerName);

  // Device Selection State
  const [showSettings, setShowSettings] = useState(false);
  const [cameras, setCameras] = useState<Array<{ deviceId: string; label: string }>>([]);
  const [mics, setMics] = useState<Array<{ deviceId: string; label: string }>>([]);
  const [speakers, setSpeakers] = useState<Array<{ deviceId: string; label: string }>>([]);
  const [selectedCamera, setSelectedCamera] = useState<string>("");
  const [selectedMic, setSelectedMic] = useState<string>("");
  const [selectedSpeaker, setSelectedSpeaker] = useState<string>("");

  const clientRef = useRef<any>(null);
  const mediaStreamRef = useRef<any>(null);
  const selfCanvasRef = useRef<HTMLCanvasElement | null>(null);
  const remoteCanvasRef = useRef<HTMLCanvasElement | null>(null);

  const loadDevices = useCallback(async () => {
    try {
      if (mediaStreamRef.current) {
        try {
          const cList = mediaStreamRef.current.getCameraList?.() || [];
          const mList = mediaStreamRef.current.getMicList?.() || [];
          const sList = mediaStreamRef.current.getSpeakerList?.() || [];
          if (cList.length > 0) setCameras(cList);
          if (mList.length > 0) setMics(mList);
          if (sList.length > 0) setSpeakers(sList);
        } catch {
          /* fallback to browser devices */
        }
      }
      if (typeof navigator !== "undefined" && navigator.mediaDevices?.enumerateDevices) {
        const allDevs = await navigator.mediaDevices.enumerateDevices();
        const videoDevs = allDevs
          .filter((d) => d.kind === "videoinput")
          .map((d, i) => ({ deviceId: d.deviceId, label: d.label || `Camera ${i + 1}` }));
        const audioInDevs = allDevs
          .filter((d) => d.kind === "audioinput")
          .map((d, i) => ({ deviceId: d.deviceId, label: d.label || `Microphone ${i + 1}` }));
        const audioOutDevs = allDevs
          .filter((d) => d.kind === "audiooutput")
          .map((d, i) => ({ deviceId: d.deviceId, label: d.label || `Speaker ${i + 1}` }));

        setCameras((prev) => (prev.length > 0 ? prev : videoDevs));
        setMics((prev) => (prev.length > 0 ? prev : audioInDevs));
        setSpeakers((prev) => (prev.length > 0 ? prev : audioOutDevs));

        if (!selectedCamera && videoDevs.length > 0) setSelectedCamera(videoDevs[0].deviceId);
        if (!selectedMic && audioInDevs.length > 0) setSelectedMic(audioInDevs[0].deviceId);
        if (!selectedSpeaker && audioOutDevs.length > 0) setSelectedSpeaker(audioOutDevs[0].deviceId);
      }
    } catch (e) {
      console.warn("Failed to enumerate media devices:", e);
    }
  }, [selectedCamera, selectedMic, selectedSpeaker]);

  const switchCameraDevice = async (deviceId: string) => {
    setSelectedCamera(deviceId);
    if (mediaStreamRef.current && deviceId) {
      try {
        await mediaStreamRef.current.switchCamera(deviceId);
        if (selfCanvasRef.current && clientRef.current) {
          await mediaStreamRef.current.renderVideo(
            selfCanvasRef.current,
            clientRef.current.getSessionInfo().userId,
            selfCanvasRef.current.width || 320,
            selfCanvasRef.current.height || 240,
            0,
            0,
            2
          );
        }
      } catch (err) {
        console.warn("Switch camera error:", err);
      }
    }
  };

  const switchMicDevice = async (deviceId: string) => {
    setSelectedMic(deviceId);
    if (mediaStreamRef.current && deviceId) {
      try {
        await mediaStreamRef.current.switchMicrophone(deviceId);
      } catch (err) {
        console.warn("Switch mic error:", err);
      }
    }
  };

  const switchSpeakerDevice = async (deviceId: string) => {
    setSelectedSpeaker(deviceId);
    if (mediaStreamRef.current && deviceId) {
      try {
        await mediaStreamRef.current.switchSpeaker(deviceId);
      } catch (err) {
        console.warn("Switch speaker error:", err);
      }
    }
  };

  // Connect to the Zoom Video SDK session
  const joinSession = useCallback(async () => {
    setConnecting(true);
    setProblem(null);

    try {
      // 1. Fetch short-lived JWT token from backend
      const sessionData = await fetchVideoSessionToken(bookingId);

      // 2. Dynamically import Zoom Video SDK on client
      const ZoomVideoModule = (await import("@zoom/videosdk")).default;
      const client = ZoomVideoModule.createClient();
      clientRef.current = client;

      // 3. Initialize SDK
      await client.init("en-US", "Global", { patchJsMedia: true });

      // 4. Join session topic with token
      await client.join(
        sessionData.session_name,
        sessionData.token,
        sessionData.user_name,
        ""
      );

      const mediaStream = client.getMediaStream();
      mediaStreamRef.current = mediaStream;

      // 5. Start audio and video
      try {
        await mediaStream.startAudio();
      } catch (aErr) {
        console.warn("Audio auto-start declined or unavailable:", aErr);
        setIsAudioMuted(true);
      }

      if (selfCanvasRef.current) {
        try {
          await mediaStream.startVideo();
          await mediaStream.renderVideo(
            selfCanvasRef.current,
            client.getSessionInfo().userId,
            selfCanvasRef.current.width || 320,
            selfCanvasRef.current.height || 240,
            0,
            0,
            2
          );
        } catch (vErr) {
          console.warn("Video auto-start declined or unavailable:", vErr);
          setIsVideoOff(true);
        }
      }

      // Check existing participants in session
      const currentParticipants = client.getAllUser();
      const otherUser = currentParticipants.find(
        (u: any) => u.userId !== client.getSessionInfo().userId
      );
      if (otherUser) {
        setRemoteUserJoined(true);
        if (otherUser.displayName) setRemoteUserName(otherUser.displayName);
        if (otherUser.bVideoOn && remoteCanvasRef.current) {
          try {
            await mediaStream.renderVideo(
              remoteCanvasRef.current,
              otherUser.userId,
              remoteCanvasRef.current.width || 640,
              remoteCanvasRef.current.height || 480,
              0,
              0,
              3
            );
          } catch (e) {
            console.warn("Error rendering remote video:", e);
          }
        }
      }

      // 6. Listen to participant events
      client.on("user-added", async (users: any[]) => {
        const u = users[0];
        if (u && u.userId !== client.getSessionInfo().userId) {
          setRemoteUserJoined(true);
          if (u.displayName) setRemoteUserName(u.displayName);
        }
      });

      client.on("user-removed", (users: any[]) => {
        const u = users[0];
        if (u && u.userId !== client.getSessionInfo().userId) {
          setRemoteUserJoined(false);
        }
      });

      client.on("peer-video-state-change", async (payload: any) => {
        if (payload.action === "Start" && remoteCanvasRef.current) {
          try {
            await mediaStream.renderVideo(
              remoteCanvasRef.current,
              payload.userId,
              remoteCanvasRef.current.width || 640,
              remoteCanvasRef.current.height || 480,
              0,
              0,
              3
            );
          } catch (e) {
            console.warn("Failed rendering peer video:", e);
          }
        } else if (payload.action === "Stop" && remoteCanvasRef.current) {
          try {
            await mediaStream.stopRenderVideo(remoteCanvasRef.current, payload.userId);
          } catch (e) {
            console.warn("Failed stopping peer video render:", e);
          }
        }
      });

      setJoined(true);
    } catch (err) {
      console.error("Failed to join Zoom Video SDK classroom:", err);
      setProblem(videoSessionProblem(err));
      setJoined(false);
    } finally {
      setConnecting(false);
    }
  }, [bookingId]);

  // Clean disconnect on component unmount
  const leaveSession = useCallback(async () => {
    try {
      if (mediaStreamRef.current) {
        if (!isVideoOff) {
          try {
            await mediaStreamRef.current.stopVideo();
          } catch {}
        }
        if (!isAudioMuted) {
          try {
            await mediaStreamRef.current.stopAudio();
          } catch {}
        }
      }
      if (clientRef.current) {
        await clientRef.current.leave();
      }
    } catch (e) {
      console.warn("Clean session leave encountered:", e);
    } finally {
      setJoined(false);
      setRemoteUserJoined(false);
      if (onLeave) onLeave();
    }
  }, [isAudioMuted, isVideoOff, onLeave]);

  useEffect(() => {
    return () => {
      void leaveSession();
    };
  }, [leaveSession]);

  // Audio mute/unmute
  const toggleAudio = async () => {
    if (!mediaStreamRef.current) return;
    try {
      if (isAudioMuted) {
        await mediaStreamRef.current.unmuteAudio();
        setIsAudioMuted(false);
      } else {
        await mediaStreamRef.current.muteAudio();
        setIsAudioMuted(true);
      }
    } catch (e) {
      console.error("Audio toggle failed:", e);
    }
  };

  // Video on/off
  const toggleVideo = async () => {
    if (!mediaStreamRef.current || !selfCanvasRef.current) return;
    try {
      if (isVideoOff) {
        await mediaStreamRef.current.startVideo();
        await mediaStreamRef.current.renderVideo(
          selfCanvasRef.current,
          clientRef.current.getSessionInfo().userId,
          selfCanvasRef.current.width || 320,
          selfCanvasRef.current.height || 240,
          0,
          0,
          2
        );
        setIsVideoOff(false);
      } else {
        await mediaStreamRef.current.stopVideo();
        setIsVideoOff(true);
      }
    } catch (e) {
      console.error("Video toggle failed:", e);
    }
  };

  // Screen share
  const toggleShareScreen = async () => {
    if (!mediaStreamRef.current) return;
    try {
      if (!isSharing) {
        await mediaStreamRef.current.startShareScreen(remoteCanvasRef.current);
        setIsSharing(true);
      } else {
        await mediaStreamRef.current.stopShareScreen();
        setIsSharing(false);
      }
    } catch (e) {
      console.error("Screen share error:", e);
      setIsSharing(false);
    }
  };

  const renderSettingsModal = () => {
    if (!showSettings) return null;
    return (
      <div
        data-testid="device-settings-modal"
        className="fixed inset-0 sm:absolute sm:inset-0 z-50 bg-slate-950/80 backdrop-blur-sm flex items-center justify-center p-4"
      >
        <div className="bg-slate-900 border border-slate-700 rounded-3xl max-w-md w-full p-5 space-y-4 shadow-2xl text-white">
          <div className="flex items-center justify-between border-b border-slate-800 pb-3">
            <div className="flex items-center gap-2">
              <Settings className="w-4 h-4 text-cocoa" />
              <h4 className="text-sm font-bold text-white">Audio &amp; Video Devices</h4>
            </div>
            <button
              type="button"
              onClick={() => setShowSettings(false)}
              className="p-1.5 rounded-xl text-slate-400 hover:text-white hover:bg-slate-800 transition-colors"
              aria-label="Close Device Settings"
            >
              <X className="w-4 h-4" />
            </button>
          </div>

          <div className="space-y-3.5 text-xs">
            {/* Camera Selection */}
            <div className="space-y-1.5">
              <label htmlFor="camera-select" className="font-semibold text-slate-300 flex items-center gap-1.5">
                <Video className="w-3.5 h-3.5 text-cocoa" />
                <span>Camera</span>
              </label>
              <select
                id="camera-select"
                aria-label="Select Camera"
                value={selectedCamera}
                onChange={(e) => void switchCameraDevice(e.target.value)}
                className="w-full bg-slate-800 border border-slate-700 rounded-xl p-2.5 text-xs text-white focus:outline-none focus:border-cocoa"
              >
                {cameras.length === 0 ? (
                  <option value="">Default System Camera</option>
                ) : (
                  cameras.map((c) => (
                    <option key={c.deviceId} value={c.deviceId}>
                      {c.label || `Camera (${c.deviceId.slice(0, 8)})`}
                    </option>
                  ))
                )}
              </select>
            </div>

            {/* Microphone Selection */}
            <div className="space-y-1.5">
              <label htmlFor="mic-select" className="font-semibold text-slate-300 flex items-center gap-1.5">
                <Mic className="w-3.5 h-3.5 text-cocoa" />
                <span>Microphone</span>
              </label>
              <select
                id="mic-select"
                aria-label="Select Microphone"
                value={selectedMic}
                onChange={(e) => void switchMicDevice(e.target.value)}
                className="w-full bg-slate-800 border border-slate-700 rounded-xl p-2.5 text-xs text-white focus:outline-none focus:border-cocoa"
              >
                {mics.length === 0 ? (
                  <option value="">Default System Microphone</option>
                ) : (
                  mics.map((m) => (
                    <option key={m.deviceId} value={m.deviceId}>
                      {m.label || `Microphone (${m.deviceId.slice(0, 8)})`}
                    </option>
                  ))
                )}
              </select>
            </div>

            {/* Speaker Selection */}
            <div className="space-y-1.5">
              <label htmlFor="speaker-select" className="font-semibold text-slate-300 flex items-center gap-1.5">
                <Volume2 className="w-3.5 h-3.5 text-cocoa" />
                <span>Speaker / Audio Output</span>
              </label>
              <select
                id="speaker-select"
                aria-label="Select Speaker"
                value={selectedSpeaker}
                onChange={(e) => void switchSpeakerDevice(e.target.value)}
                className="w-full bg-slate-800 border border-slate-700 rounded-xl p-2.5 text-xs text-white focus:outline-none focus:border-cocoa"
              >
                {speakers.length === 0 ? (
                  <option value="">Default System Speaker</option>
                ) : (
                  speakers.map((s) => (
                    <option key={s.deviceId} value={s.deviceId}>
                      {s.label || `Speaker (${s.deviceId.slice(0, 8)})`}
                    </option>
                  ))
                )}
              </select>
            </div>
          </div>

          <div className="pt-2 border-t border-slate-800 flex justify-end">
            <button
              type="button"
              onClick={() => setShowSettings(false)}
              className="px-4 py-2 rounded-xl bg-cocoa text-slate-950 font-bold text-xs hover:bg-cocoa-hover transition-colors"
            >
              Done
            </button>
          </div>
        </div>
      </div>
    );
  };

  // Not connected yet: display pre-join stage
  if (!joined) {
    return (
      <div className="bg-slate-900 rounded-3xl p-6 sm:p-8 text-white space-y-6 shadow-xl relative overflow-hidden border border-slate-800">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <span className="w-2.5 h-2.5 rounded-full bg-cocoa animate-pulse" />
            <span className="text-xs font-bold uppercase tracking-wider text-cocoa">
              In-Browser Classroom
            </span>
          </div>
          <span className="text-[11px] text-slate-400 flex items-center gap-1">
            <ShieldCheck className="w-3.5 h-3.5 text-cocoa" /> WebRTC HD
          </span>
        </div>

        <div className="text-center py-8 space-y-4">
          <div className="w-20 h-20 rounded-3xl bg-slate-800 border border-slate-700 mx-auto flex items-center justify-center text-cocoa shadow-inner">
            <Video className="w-10 h-10" />
          </div>
          <div className="space-y-1">
            <h3 className="text-lg font-bold">Live Synchronous Classroom</h3>
            <p className="text-xs text-slate-400 max-w-sm mx-auto">
              Your lesson with <span className="text-white font-medium">{partnerName}</span> runs
              directly in this browser tab. No Zoom app or download required.
            </p>
          </div>

          {problem && (
            <div className="p-3.5 rounded-2xl bg-amber-500/10 border border-amber-500/20 text-xs text-amber-200 max-w-md mx-auto flex items-start gap-2.5 text-left">
              <AlertTriangle className="w-4 h-4 text-amber-400 shrink-0 mt-0.5" />
              <span>{problem.message}</span>
            </div>
          )}

          <div className="pt-2 flex flex-col sm:flex-row items-center justify-center gap-3">
            <button
              type="button"
              onClick={joinSession}
              disabled={connecting}
              className="w-full sm:w-auto px-6 py-3 rounded-2xl bg-cocoa text-slate-950 font-black text-sm hover:bg-cocoa-hover transition-all flex items-center justify-center gap-2 shadow-lg disabled:opacity-50"
            >
              {connecting ? (
                <>
                  <Loader2 className="w-4 h-4 animate-spin" />
                  <span>Connecting to Classroom...</span>
                </>
              ) : (
                <>
                  <Video className="w-4 h-4" />
                  <span>{isHost ? "Open Classroom as Host" : "Enter Classroom"}</span>
                </>
              )}
            </button>

            <button
              type="button"
              onClick={() => {
                setShowSettings(true);
                void loadDevices();
              }}
              className="w-full sm:w-auto px-4 py-3 rounded-2xl bg-slate-800 text-slate-300 font-bold text-xs hover:bg-slate-700 transition-all flex items-center justify-center gap-1.5 border border-slate-700"
            >
              <Settings className="w-3.5 h-3.5 text-cocoa" />
              <span>Device Settings</span>
            </button>

            {legacyJoinUrl && (
              <a
                href={legacyJoinUrl}
                target="_blank"
                rel="noopener noreferrer"
                className="w-full sm:w-auto px-4 py-3 rounded-2xl bg-slate-800 text-slate-300 font-bold text-xs hover:bg-slate-700 transition-all flex items-center justify-center gap-1.5 border border-slate-700"
              >
                <span>Launch in Zoom App</span>
                <ExternalLink className="w-3.5 h-3.5" />
              </a>
            )}
          </div>
        </div>

        {renderSettingsModal()}
      </div>
    );
  }

  // Active in-browser video call stage
  return (
    <div className="bg-slate-950 rounded-3xl overflow-hidden shadow-2xl border border-slate-800 relative flex flex-col min-h-[460px] lg:min-h-[540px]">
      {/* Top Header Pill */}
      <div className="absolute top-4 left-4 right-4 z-20 flex items-center justify-between pointer-events-none">
        <div className="bg-slate-900/90 backdrop-blur-md px-3.5 py-1.5 rounded-full border border-slate-700/60 shadow-md flex items-center gap-2 pointer-events-auto">
          <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
          <span className="text-xs font-bold text-white">Live · {remoteUserName}</span>
        </div>

        <div className="bg-slate-900/90 backdrop-blur-md px-3 py-1.5 rounded-full border border-slate-700/60 shadow-md flex items-center gap-1.5 text-[11px] text-slate-300 pointer-events-auto">
          <ShieldCheck className="w-3.5 h-3.5 text-cocoa" />
          <span>Encrypted Session</span>
        </div>
      </div>

      {/* Main Remote Video Feed */}
      <div className="relative flex-1 bg-slate-900 flex items-center justify-center overflow-hidden">
        <canvas
          ref={remoteCanvasRef}
          width={640}
          height={480}
          className={`w-full h-full object-cover ${remoteUserJoined ? "block" : "hidden"}`}
        />

        {!remoteUserJoined && (
          <div className="text-center p-8 space-y-3 z-10">
            <div className="w-20 h-20 rounded-full bg-slate-800 border border-slate-700 mx-auto flex items-center justify-center text-slate-400 overflow-hidden shadow-inner">
              {partnerAvatar ? (
                <img src={partnerAvatar} alt={partnerName} className="w-full h-full object-cover" />
              ) : (
                <User className="w-10 h-10 text-slate-500" />
              )}
            </div>
            <div className="space-y-1">
              <p className="text-sm font-bold text-white">Waiting for {partnerName} to join...</p>
              <p className="text-xs text-slate-400">
                You are in the classroom. The video will start automatically when they connect.
              </p>
            </div>
          </div>
        )}

        {/* Self Picture-in-Picture Preview */}
        <div className="absolute bottom-20 right-2 sm:right-4 z-20 w-28 h-20 sm:w-44 sm:h-32 rounded-2xl overflow-hidden border-2 border-slate-700/80 shadow-2xl bg-slate-950">
          <canvas
            ref={selfCanvasRef}
            width={320}
            height={240}
            className={`w-full h-full object-cover ${isVideoOff ? "hidden" : "block"}`}
          />
          {isVideoOff && (
            <div className="w-full h-full flex flex-col items-center justify-center bg-slate-900 text-slate-500 text-[10px] font-bold">
              <VideoOff className="w-5 h-5 mb-1 text-slate-600" />
              <span>Camera Off</span>
            </div>
          )}
          <span className="absolute bottom-1.5 left-2 text-[10px] font-bold bg-slate-900/80 px-1.5 py-0.5 rounded text-white backdrop-blur-xs">
            You
          </span>
        </div>
      </div>

      {/* Bottom Floating Classroom Control Bar */}
      <div className="bg-slate-900/95 backdrop-blur-lg border-t border-slate-800/80 px-3 py-3 sm:px-6 sm:py-4 flex items-center justify-between z-20 gap-2">
        <div className="flex items-center gap-1.5 sm:gap-2">
          {/* Microphone Mute/Unmute */}
          <button
            type="button"
            onClick={toggleAudio}
            className={`p-2.5 sm:p-3 rounded-2xl transition-all shadow-sm ${
              isAudioMuted
                ? "bg-rose-500/20 text-rose-400 border border-rose-500/30 hover:bg-rose-500/30"
                : "bg-slate-800 text-white hover:bg-slate-700 border border-slate-700"
            }`}
            title={isAudioMuted ? "Unmute Microphone" : "Mute Microphone"}
            aria-label={isAudioMuted ? "Unmute Microphone" : "Mute Microphone"}
          >
            {isAudioMuted ? <MicOff className="w-4 h-4 sm:w-5 sm:h-5" /> : <Mic className="w-4 h-4 sm:w-5 sm:h-5" />}
          </button>

          {/* Camera On/Off */}
          <button
            type="button"
            onClick={toggleVideo}
            className={`p-2.5 sm:p-3 rounded-2xl transition-all shadow-sm ${
              isVideoOff
                ? "bg-rose-500/20 text-rose-400 border border-rose-500/30 hover:bg-rose-500/30"
                : "bg-slate-800 text-white hover:bg-slate-700 border border-slate-700"
            }`}
            title={isVideoOff ? "Turn Video On" : "Turn Video Off"}
            aria-label={isVideoOff ? "Turn Video On" : "Turn Video Off"}
          >
            {isVideoOff ? <VideoOff className="w-4 h-4 sm:w-5 sm:h-5" /> : <Video className="w-4 h-4 sm:w-5 sm:h-5" />}
          </button>

          {/* Screen Share */}
          <button
            type="button"
            onClick={toggleShareScreen}
            className={`p-2.5 sm:p-3 rounded-2xl transition-all hidden sm:flex shadow-sm ${
              isSharing
                ? "bg-cocoa text-slate-950 hover:bg-cocoa-hover"
                : "bg-slate-800 text-white hover:bg-slate-700 border border-slate-700"
            }`}
            title={isSharing ? "Stop Sharing Screen" : "Share Screen"}
            aria-label={isSharing ? "Stop Sharing Screen" : "Share Screen"}
          >
            <Share2 className="w-4 h-4 sm:w-5 sm:h-5" />
          </button>

          {/* Settings / Device Selection */}
          <button
            type="button"
            onClick={() => {
              setShowSettings((prev) => !prev);
              void loadDevices();
            }}
            className={`p-2.5 sm:p-3 rounded-2xl transition-all shadow-sm ${
              showSettings
                ? "bg-cocoa text-slate-950 hover:bg-cocoa-hover"
                : "bg-slate-800 text-white hover:bg-slate-700 border border-slate-700"
            }`}
            title="Audio & Video Devices"
            aria-label="Device Settings"
          >
            <Settings className="w-4 h-4 sm:w-5 sm:h-5" />
          </button>
        </div>

        {/* Leave / End Lesson Button */}
        <button
          type="button"
          onClick={leaveSession}
          className="px-3 py-2 sm:px-5 sm:py-2.5 rounded-2xl bg-rose-600 text-white font-bold text-xs hover:bg-rose-700 transition-all flex items-center gap-1.5 sm:gap-2 shadow-lg shrink-0"
        >
          <PhoneOff className="w-3.5 h-3.5 sm:w-4 sm:h-4" />
          <span>Leave Room</span>
        </button>
      </div>

      {renderSettingsModal()}
    </div>
  );
}
