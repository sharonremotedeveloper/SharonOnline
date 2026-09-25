import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./src/pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/components/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        brand: {
          50: '#F0F7F6',
          100: '#DDEFEA',
          200: '#BBDDD5',
          300: '#8BC3B8',
          400: '#5BA498',
          500: '#3D887C',
          600: '#2C6D63',
          700: '#1D534B',
          800: '#15433D',
          900: '#0D4440', // Primary signature deep teal
          950: '#062523',
        },
        gold: {
          500: '#E6A838', // Warm accent gold
          600: '#D49422',
        },
        surface: {
          DEFAULT: '#F7FAF9',
          card: '#FFFFFF',
          muted: '#F0F4F3',
        }
      },
      boxShadow: {
        'card': '0 2px 8px -2px rgba(13, 68, 64, 0.08), 0 1px 4px -1px rgba(13, 68, 64, 0.04)',
        'card-hover': '0 12px 24px -6px rgba(13, 68, 64, 0.12), 0 4px 8px -2px rgba(13, 68, 64, 0.06)',
      }
    },
  },
  plugins: [],
};
export default config;
