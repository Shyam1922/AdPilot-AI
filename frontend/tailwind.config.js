/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        brand: {
          DEFAULT: "#8b5cf6",
          50: "#241640",
          100: "#2e1b54",
          200: "#c4b5fd",
          300: "#d6ccfe",
          400: "#a78bfa",
          500: "#8b5cf6",
          600: "#7c3aed",
          700: "#6d28d9",
        },
        ink: "#f1edfa",
        muted: "#a79cc4",
        surface: "#1d1236",
        "surface-2": "#271a44",
        canvas: "#140b24",
        line: "#312449",
        success: "#34d399",
        warn: "#fbbf24",
        danger: "#f87171",
        sim: "#fbbf24",
        sidebar: "#120a22",
        "sidebar-hover": "#241640",
      },
      fontFamily: {
        sans: ["Inter", "ui-sans-serif", "system-ui", "sans-serif"],
        serif: ["Lora", "ui-serif", "Georgia", "serif"],
      },
      borderColor: {
        DEFAULT: "#312449",
      },
      borderRadius: {
        xl: "0.875rem",
      },
      boxShadow: {
        card: "0 1px 2px rgba(0,0,0,0.3), 0 1px 3px rgba(0,0,0,0.35)",
        panel: "0 8px 30px rgba(0,0,0,0.45)",
      },
    },
  },
  plugins: [],
};
