import type { Config } from "tailwindcss";

/*
 * CONTRAST LEDGER (WCAG 2.x, computed with a script, relative luminance)
 * Text pairs (need >= 4.5):
 *   ink #2D2521 on sun #FFDE3D 11.28 | cocoa #4A2C1A on sun 9.46 | white on cocoa 12.60 | cream #FFF8F2 on cocoa 11.98
 *   sun #FFDE3D on cocoa 9.46 | on cocoa-deep #361F12 11.58 | ink-300 #B8A89F on cocoa 5.48 | #CDBBB0 on cocoa 6.80
 *   primary #C2410C on white 5.18 | on cream 4.92 | on sun-soft #FFF3A8 4.60 (never on sun/sky/peach solid)
 *   ink-faint/400 #6F5E55 on cream 5.86 | cream-deep 5.07 | white 6.16 | sun 4.63 | sky-soft 5.31 | peach 4.69
 *   ink-muted #6B5B53 on cream 6.15 | cream-deep 5.33   (old faint #8A746A was 4.17 on cream: failed)
 *   success #0B5C85 on white 7.28 | cream 6.92 | success-surface #E8F4FB 6.51 | white on success 7.28
 *   warning #7A4B00 on white 7.41 | warning-surface #FFE9CC (orange tint, not sun yellow) 6.27 | on sun 5.56 | white on warning 7.41
 *   info #4A3A32 (neutral cocoa-ink) on info-surface #F1E9E1 (neutral cream-grey, clearly unlike success #E8F4FB) 9.00 | white 10.81 | cream 10.28
 *   error #B83232 on white 5.93 | error-surface 5.33 | cream 5.64 | white on error 5.93 | white on error-hover #8F2A1F 8.34
 * Non-text (need >= 3:1):
 *   border-strong #85705F on white 4.69 | cream 4.46 | cream-deep 3.86
 *   star #B07400 on white 3.93 | cream 3.74 | (3.24 on cream-deep)
 * Decorative only (no ratio required): divider #E4D3C6 (1.38 on cream).
 */
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
          faint: "#6F5E55",
          light: "#6F5E55",
          300: "#B8A89F",
          400: "#6F5E55",
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
        // Opaque base for floating panels (drawers, modals, popovers). Was used as `bg-surface` but never defined.
        surface: { DEFAULT: "#FFFFFF" },
        // Status colours. Deliberately not green/teal/amber: success is a deep cerulean, warning a dark gold-brown on a
        // orange tint (never the sun yellow, which is neutral), info a neutral cocoa-ink on sky-tint (so it never reads as success). Always pair with an icon or a word, never colour alone.
        success: {
          DEFAULT: "#0B5C85",
          hover: "#08455F",
          surface: "#E8F4FB",
          border: "#8CC4E4",
        },
        warning: {
          DEFAULT: "#7A4B00",
          hover: "#5C3700",
          surface: "#FFE9CC",
          border: "#D98A2B",
        },
        info: {
          DEFAULT: "#4A3A32",
          hover: "#2D2521",
          surface: "#F1E9E1",
          border: "#CDBBB0",
        },
        error: {
          DEFAULT: "#B83232",
          hover: "#8F2A1F",
          surface: "#FDF0EE",
          border: "#F0B4AC",
        },
        // Star ratings: a darker gold that holds 3:1 as a graphic on white and cream (never use `gold` for text or icons on light).
        star: "#B07400",
      },
      // Form-control and interactive borders. 3:1 or better against white, cream and cream-deep. `divider` stays light (decorative).
      borderColor: {
        strong: "#85705F",
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
