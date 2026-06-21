/** @type {import('tailwindcss').Config} */
export default {
  darkMode: 'media',
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        cream: '#FBF7F0',
        'near-black': '#16161A',
        surface: {
          light: '#FFFFFF',
          dark: '#1E1E24',
        },
        accent: {
          DEFAULT: '#6D5EF6',
          dark: '#8B7CFA',
        },
        teal: {
          DEFAULT: '#14B8A6',
          dark: '#2DD4BF',
        },
      },
      fontFamily: {
        sans: ['Inter', 'ui-sans-serif', 'system-ui', 'sans-serif'],
      },
      keyframes: {
        'fade-in': {
          '0%': { opacity: '0' },
          '100%': { opacity: '1' },
        },
      },
      animation: {
        'fade-in': 'fade-in 0.5s ease-out forwards',
      },
    },
  },
  plugins: [],
}
