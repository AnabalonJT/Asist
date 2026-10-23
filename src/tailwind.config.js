/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './pages/**/*.{ts,tsx}', './components/**/*.{ts,tsx}', './hooks/**/*.{ts,tsx}', './lib/**/*.{ts,tsx}', './main.tsx'],
  theme: {
    extend: {
      fontFamily: {
        sans: ['Barlow', 'system-ui', 'sans-serif'],
        display: ['"Barlow Condensed"', 'Barlow', 'system-ui', 'sans-serif'],
        mono: ['JetBrains Mono', 'monospace'],
      },
      colors: {
        bg: {
          base: '#0d0f14',
          surface: '#13161e',
          elevated: '#1a1e29',
          border: '#232840',
        },
        accent: {
          DEFAULT: '#f97316',
          dim: '#9a4a12',
          hover: '#fb8a3c',
          glow: 'rgba(249,115,22,0.14)',
        },
        text: {
          primary: '#e8eaf0',
          secondary: '#8891a8',
          dim: '#4a5168',
        },
        success: '#22c55e',
        'success-glow': 'rgba(34,197,94,0.14)',
        warning: '#fbbf24',
        danger: '#f87171',
        tg: '#229ED9',
      },
      boxShadow: {
        glow: '0 0 28px rgba(249,115,22,0.16)',
        card: '0 1px 3px rgba(0,0,0,0.4)',
      },
    },
  },
  plugins: [],
}
