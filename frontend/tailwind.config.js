/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      // Monochrome, near-black palette: white is the accent, grey carries hierarchy.
      colors: {
        canvas: "#000000",
        surface: "#111315",
        "surface-2": "#191a1d",
        raised: "#212121",
        line: "#26272b",
        ink: "#ededed",
        body: "#d9d9d9",
        muted: "#848484",
        success: "#34d399",
        warn: "#fbbf24",
        danger: "#f87171",
        sim: "#fbbf24",
      },
      fontFamily: {
        sans: ["Geist", "ui-sans-serif", "system-ui", "sans-serif"],
        serif: ["Newsreader", "ui-serif", "Georgia", "serif"],
      },
      borderColor: {
        DEFAULT: "#26272b",
      },
      borderRadius: {
        xl: "0.75rem",
        "2xl": "1rem",
      },
      boxShadow: {
        card: "none",
        panel:
          "0 14px 31px rgba(0,0,0,0.25), 0 55px 55px rgba(0,0,0,0.2), 0 125px 75px rgba(0,0,0,0.1)",
      },
      letterSpacing: {
        nav: "0.03em",
      },
    },
  },
  plugins: [],
};
