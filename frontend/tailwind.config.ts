import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./src/pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/components/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      fontFamily: {
        sans: ["var(--font-dm-sans)", "DM Sans", "system-ui", "sans-serif"],
        serif: ["var(--font-lora)", "Lora", "Georgia", "serif"],
      },
      colors: {
        cream: {
          DEFAULT: "#FFF8F2",
          deep: "#F4E7DA",
          surface: "#FFF4EA",
        },
        ink: {
          DEFAULT: "#2D2521",
          muted: "#6B5B53",
          faint: "#8A746A",
        },
        primary: {
          DEFAULT: "#C2410C",
          hover: "#9A3412",
          surface: "#FFF4EA",
        },
        terracotta: {
          DEFAULT: "#A94332",
          hover: "#873426",
          surface: "#FFF4EA",
        },
        gold: {
          DEFAULT: "#E7A83E",
          hover: "#D6962E",
          surface: "#FAF0DC",
          bright: "#D4A84B",
        },
        // Brand dark: warm near-black (the old cold green, then a plum, were both dropped). Same token as before so
        // every "cocoa" class follows. Surface and border are soft yellow tints.
        cocoa: {
          DEFAULT: "#201A17",
          hover: "#120F0D",
          deep: "#120F0D",
          mid: "#3A302B",
          surface: "#FFF6CC",
          border: "#EFE0A0",
        },
        // Cambly-style accents: sunny yellow, coral and sky blue for colour-blocked sections and highlights
        sun: { DEFAULT: "#FFDE3D", soft: "#FFF3A8" },
        coral: { DEFAULT: "#FF6B4A", soft: "#FFD6CB" },
        sky: { DEFAULT: "#9ED8FF", soft: "#DDF1FF" },
        peach: { DEFAULT: "#FFD9C4", soft: "#FFEDE2" },
        plum: {
          DEFAULT: "#4A2948",
          surface: "#FFF1E6",
        },
        divider: "#E4D3C6",
        success: {
          DEFAULT: "#52705A",
          surface: "#EEF3EC",
        },
        error: {
          DEFAULT: "#B83232",
          surface: "#FDF0EE",
        },
      },
      boxShadow: {
        card: "0 1px 3px rgba(45, 37, 33, 0.07), 0 8px 24px rgba(45, 37, 33, 0.05)",
        "card-hover": "0 2px 6px rgba(45, 37, 33, 0.08), 0 16px 34px rgba(45, 37, 33, 0.08)",
        "card-sm": "0 1px 4px rgba(45, 37, 33, 0.07)",
      },
      borderRadius: {
        sm: "6px",
        md: "10px",
        lg: "14px",
        xl: "20px",
      },
    },
  },
  plugins: [],
};
export default config;
