import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./src/**/*.{js,ts,jsx,tsx,mdx}"],
  theme: {
    extend: {
      colors: {
        navy: {
          50: "#f0f4f9",
          100: "#dbe5f0",
          200: "#b3c7dd",
          300: "#84a3c4",
          400: "#5b80a8",
          500: "#3d638c",
          600: "#2c4d70",
          700: "#213a56",
          800: "#16263c",
          900: "#0c1420",
          950: "#080d16",
        },
        teal: {
          50: "#effcfa",
          100: "#d6f6f1",
          200: "#adece4",
          300: "#7bdcd2",
          400: "#45c2b7",
          500: "#26a69c",
          600: "#1b847d",
          700: "#186a66",
          800: "#175552",
          900: "#164846",
          950: "#082826",
        },
        success: "#1a9e5c",
        warning: "#b8720b",
        danger: "#c0362c",
      },
      fontFamily: {
        sans: ["var(--font-inter)", "ui-sans-serif", "system-ui", "sans-serif"],
      },
      boxShadow: {
        card: "0 1px 2px 0 rgba(16, 24, 40, 0.06), 0 1px 3px 0 rgba(16, 24, 40, 0.10)",
        dropdown: "0 4px 6px -2px rgba(16, 24, 40, 0.05), 0 12px 16px -4px rgba(16, 24, 40, 0.10)",
        "focus-ring": "0 0 0 3px rgba(38, 166, 156, 0.35)",
      },
      borderRadius: {
        xl: "0.75rem",
      },
      keyframes: {
        shimmer: {
          "0%": { backgroundPosition: "-200% 0" },
          "100%": { backgroundPosition: "200% 0" },
        },
        "fade-in": {
          from: { opacity: "0" },
          to: { opacity: "1" },
        },
        "slide-up": {
          from: { opacity: "0", transform: "translateY(8px)" },
          to: { opacity: "1", transform: "translateY(0)" },
        },
        "slide-in-right": {
          from: { opacity: "0", transform: "translateX(16px)" },
          to: { opacity: "1", transform: "translateX(0)" },
        },
      },
      animation: {
        shimmer: "shimmer 1.6s ease-in-out infinite",
        "fade-in": "fade-in 150ms ease-out",
        "slide-up": "slide-up 200ms ease-out",
        "slide-in-right": "slide-in-right 200ms ease-out",
      },
      zIndex: {
        "60": "60",
      },
    },
  },
  plugins: [],
};

export default config;
