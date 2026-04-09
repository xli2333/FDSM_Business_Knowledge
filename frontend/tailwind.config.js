/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        fudan: {
          blue: '#0d0783', // Extracted primary color
          dark: '#0a0560',
          light: '#f4f4f5', // Very light gray for background contrast
        }
      },
      fontFamily: {
        sans: ['Inter', 'Noto Sans SC', 'system-ui', 'sans-serif'],
        serif: ['Noto Serif SC', 'Playfair Display', 'Songti SC', 'serif'],
      },
      spacing: {
        '128': '32rem',
        '144': '36rem',
      }
    },
  },
  plugins: [],
}