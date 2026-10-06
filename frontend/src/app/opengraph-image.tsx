import { ImageResponse } from "next/og";

// A real PNG: LINE, KakaoTalk, Facebook and X do not render the SVG that used to be referenced here.
export const alt = "Sharon Online: 1-on-1 English lessons with friendly South African tutors";
export const size = { width: 1200, height: 630 };
export const contentType = "image/png";

export default function OpengraphImage() {
  return new ImageResponse(
    (
      <div
        style={{
          width: "100%",
          height: "100%",
          display: "flex",
          flexDirection: "column",
          justifyContent: "center",
          padding: 80,
          background: "linear-gradient(135deg, #201A17 0%, #120F0D 100%)",
          color: "white",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 20, marginBottom: 48 }}>
          <div
            style={{
              width: 72,
              height: 72,
              borderRadius: 18,
              background: "#E7A83E",
              color: "#201A17",
              fontSize: 48,
              fontWeight: 700,
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
            }}
          >
            S
          </div>
          <div style={{ fontSize: 44, fontWeight: 700 }}>Sharon Online</div>
        </div>
        <div style={{ fontSize: 76, fontWeight: 800, lineHeight: 1.1, display: "flex", flexWrap: "wrap" }}>
          Speak English with confidence.
        </div>
        <div style={{ fontSize: 34, marginTop: 28, color: "#D4A84B", display: "flex" }}>
          Private 25-minute lessons with friendly South African tutors
        </div>
      </div>
    ),
    size,
  );
}
