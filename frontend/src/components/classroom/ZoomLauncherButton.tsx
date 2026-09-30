"use client";

import { useState } from "react";
import { Video, ExternalLink, Copy, Check, Monitor, Globe } from "lucide-react";

interface ZoomLauncherButtonProps {
  meetingId: string;
  password?: string;
  joinUrl: string;
  startUrl?: string;
  isHost?: boolean;
  disabled?: boolean;
  className?: string;
}

export function ZoomLauncherButton({
  meetingId,
  password = "",
  joinUrl,
  startUrl,
  isHost = false,
  disabled = false,
  className = "",
}: ZoomLauncherButtonProps) {
  const [copiedId, setCopiedId] = useState(false);
  const [copiedPwd, setCopiedPwd] = useState(false);
  const [preferWeb, setPreferWeb] = useState(false);

  const cleanConfNo = meetingId.replace(/\s+/g, "");

  // Deep link Zoom URI
  const appDeepLink = isHost && startUrl
    ? startUrl
    : `zoommtg://zoom.us/join?confno=${cleanConfNo}&pwd=${encodeURIComponent(password)}`;

  // Web client URL fallback
  const webClientUrl = `https://zoom.us/wc/${cleanConfNo}/join?pwd=${encodeURIComponent(password)}`;

  const targetUrl = preferWeb ? webClientUrl : (isHost && startUrl ? startUrl : appDeepLink);

  const handleLaunch = () => {
    if (disabled) return;
    if (preferWeb) {
      window.open(webClientUrl, "_blank", "noopener,noreferrer");
    } else {
      // First attempt to open the native desktop zoom protocol
      window.location.href = appDeepLink;
      // Fallback timer: if browser doesn't have Zoom installed, give user web link option
      setTimeout(() => {
        const confirmWeb = window.confirm(
          "Did Zoom open? If you don't have the Zoom desktop app installed, click OK to join via your Web Browser."
        );
        if (confirmWeb) {
          window.open(webClientUrl, "_blank", "noopener,noreferrer");
        }
      }, 2500);
    }
  };

  const copyToClipboard = (text: string, isPwd = false) => {
    if (typeof window !== "undefined") {
      navigator.clipboard.writeText(text);
      if (isPwd) {
        setCopiedPwd(true);
        setTimeout(() => setCopiedPwd(false), 2000);
      } else {
        setCopiedId(true);
        setTimeout(() => setCopiedId(false), 2000);
      }
    }
  };

  return (
    <div className={`space-y-4 ${className}`}>
      {/* Primary Action Button */}
      <div className="space-y-2">
        <button
          type="button"
          onClick={handleLaunch}
          disabled={disabled}
          className={`w-full py-4 px-6 rounded-2xl font-black text-sm flex items-center justify-center gap-3 transition-all shadow-lg ${
            disabled
              ? "bg-cream-surface text-ink-muted/50 cursor-not-allowed border border-divider"
              : isHost
              ? "bg-accent hover:bg-amber-600 text-ink shadow-accent/20 hover:scale-[1.01]"
              : "bg-teal hover:bg-teal-hover text-white shadow-teal/20 hover:scale-[1.01]"
          }`}
        >
          <Video className="w-5 h-5" />
          <span>
            {disabled
              ? "Lesson Not Yet Open"
              : isHost
              ? "Start Lesson as Host (Zoom)"
              : "Join Live Lesson in Zoom"}
          </span>
          <ExternalLink className="w-4 h-4 opacity-75" />
        </button>

        {/* Client Protocol Preference Selector */}
        <div className="flex items-center justify-center gap-4 text-xs font-semibold text-ink-muted pt-1">
          <button
            type="button"
            onClick={() => setPreferWeb(false)}
            className={`flex items-center gap-1.5 px-3 py-1 rounded-lg transition-colors ${
              !preferWeb ? "bg-cream-surface text-teal font-bold border border-divider" : "hover:text-ink"
            }`}
          >
            <Monitor className="w-3.5 h-3.5" />
            <span>Open in Zoom App (Recommended)</span>
          </button>

          <button
            type="button"
            onClick={() => setPreferWeb(true)}
            className={`flex items-center gap-1.5 px-3 py-1 rounded-lg transition-colors ${
              preferWeb ? "bg-cream-surface text-teal font-bold border border-divider" : "hover:text-ink"
            }`}
          >
            <Globe className="w-3.5 h-3.5" />
            <span>Join in Web Browser</span>
          </button>
        </div>
      </div>

      {/* Manual Meeting Credentials Snippet */}
      <div className="p-4 rounded-2xl bg-cream-surface border border-divider flex flex-wrap items-center justify-between gap-3 text-xs">
        <div className="flex items-center gap-4">
          <div>
            <span className="text-[10px] uppercase tracking-wider text-ink-muted block font-bold">Meeting ID</span>
            <span className="font-mono font-bold text-ink">{cleanConfNo || "987 654 3210"}</span>
          </div>

          <button
            type="button"
            onClick={() => copyToClipboard(cleanConfNo || "9876543210", false)}
            className="p-1.5 rounded-lg bg-white hover:bg-cream-deep text-ink-muted hover:text-ink border border-divider transition-colors"
            title="Copy Meeting ID"
          >
            {copiedId ? <Check className="w-3.5 h-3.5 text-success" /> : <Copy className="w-3.5 h-3.5" />}
          </button>

          {password && (
            <>
              <div className="border-l border-divider pl-4">
                <span className="text-[10px] uppercase tracking-wider text-ink-muted block font-bold">Passcode</span>
                <span className="font-mono font-bold text-ink">{password}</span>
              </div>

              <button
                type="button"
                onClick={() => copyToClipboard(password, true)}
                className="p-1.5 rounded-lg bg-white hover:bg-cream-deep text-ink-muted hover:text-ink border border-divider transition-colors"
                title="Copy Passcode"
              >
                {copiedPwd ? <Check className="w-3.5 h-3.5 text-success" /> : <Copy className="w-3.5 h-3.5" />}
              </button>
            </>
          )}
        </div>

        <a
          href={joinUrl}
          target="_blank"
          rel="noopener noreferrer"
          className="text-xs font-bold text-teal hover:underline flex items-center gap-1"
        >
          Direct Web Link <ExternalLink className="w-3 h-3" />
        </a>
      </div>
    </div>
  );
}
