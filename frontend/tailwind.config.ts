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
          50: "#FFFCF8",
          100: "#FFF8F2",
          200: "#F4E7DA",
          300: "#E4D3C6",
        },
        ink: {
          DEFAULT: "#2D2521",
          muted: "#6B5B53",
          faint: "#8A746A",
          light: "#8A746A",
          300: "#B8A89F",
          400: "#8A746A",
          500: "#6B5B53",
          600: "#55463F",
          700: "#43362F",
          800: "#2D2521",
          900: "#2D2521",
          950: "#1A1512",
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
        // Brand dark: warm chocolate brown (rolled from near-black #201A17 / #120F0D; earlier a cold green, then a plum). Same token as before so
        // every "cocoa" class follows. Surface and border are soft yellow tints.
        cocoa: {
          DEFAULT: "#4A2C1A",
          hover: "#361F12",
          deep: "#361F12",
          mid: "#5E3A25",
          surface: "#FFF6CC",
          border: "#EFE0A0",
          // Numeric scale used by older pages: light warm neutrals, then browns, then near-black
          50: "#FBF3E8",
          100: "#F4E7DA",
          200: "#E9CDBD",
          300: "#B8A89F",
          400: "#8A746A",
          500: "#6B4530",
          600: "#4A2C1A",
          700: "#361F12",
          800: "#361F12",
          900: "#2A170D",
          950: "#1C0F08",
        },
        // The accent used for gold-style calls to action in older pages: now the brand yellow
        accent: {
          DEFAULT: "#FFDE3D",
          surface: "#FFF3A8",
          300: "#FFE97A",
          400: "#FFDE3D",
          500: "#F2C500",
          600: "#C79B00",
        },
        // Cambly-style accents: sunny yellow, coral and sky blue for colour-blocked sections and highlights
        sun: { DEFAULT: "#FFDE3D", soft: "#FFF3A8" },
        coral: { DEFAULT: "#FF6B4A", soft: "#FFD6CB" },
        sky: { DEFAULT: "#9ED8FF", soft: "#DDF1FF" },
        peach: { DEFAULT: "#FFD9C4", soft: "#FFEDE2" },
        plum: {
          DEFAULT: "#8A3B1F",
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
