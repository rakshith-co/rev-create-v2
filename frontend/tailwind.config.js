/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        brand: {
          50: "#f5f3ff",
          500: "#6d28d9",
          600: "#5b21b6",
          700: "#4c1d95",
        },
      },
    },
  },
  plugins: [],
};
