/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        bg: {
          base: "#07080c",
          surface: "#0f1117",
          elevated: "#161b25",
          border: "#1e2535",
        },
        accent: {
          green: "#00e87a",
          amber: "#ffb800",
          red: "#ff4545",
          blue: "#4d9fff",
          purple: "#a78bfa",
        },
        text: {
          primary: "#e8edf5",
          secondary: "#7a8499",
          muted: "#3d4558",
        },
      },
      fontFamily: {
        sans: ["'DM Sans'", "system-ui", "sans-serif"],
        mono: ["'JetBrains Mono'", "monospace"],
      },
      backgroundImage: {
        "grid-dots": "radial-gradient(circle, #1e2535 1px, transparent 1px)",
      },
      backgroundSize: {
        "grid-dots": "28px 28px",
      },
    },
  },
  plugins: [],
};
