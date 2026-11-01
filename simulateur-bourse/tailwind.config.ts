import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./src/app/**/*.{ts,tsx}",
    "./src/components/**/*.{ts,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        // Palette sombre "trading"
        base: {
          900: "#0b0f17",
          800: "#111827",
          700: "#1a2333",
          600: "#243044",
        },
        brand: {
          DEFAULT: "#10b981",
          500: "#10b981",
          600: "#059669",
        },
        gain: "#22c55e",
        loss: "#ef4444",
      },
      fontFamily: {
        sans: ["var(--font-sans)", "system-ui", "sans-serif"],
      },
    },
  },
  plugins: [],
};

export default config;
