/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './pages/**/*.{ts,tsx}', './components/**/*.{ts,tsx}', './hooks/**/*.{ts,tsx}', './lib/**/*.{ts,tsx}', './main.tsx'],
  theme: {
    extend: {
      fontFamily: {
        sans: ['Inter', 'system-ui', 'sans-serif'],
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
          DEFAULT: '#6c8cff',
          dim: '#3a4f99',
          glow: 'rgba(108,140,255,0.15)',
        },
        text: {
          primary: '#e8eaf0',
          secondary: '#8891a8',
          dim: '#4a5168',
        },
        success: '#4ade80',
        warning: '#fbbf24',
        danger: '#f87171',
        tg: '#229ED9',
      },
      boxShadow: {
        glow: '0 0 24px rgba(108,140,255,0.12)',
        card: '0 1px 3px rgba(0,0,0,0.4)',
      },
    },
  },
  plugins: [],
}
