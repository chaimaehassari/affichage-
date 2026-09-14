import { useState, useEffect } from 'react'
import { Sun, Moon } from 'lucide-react'

const STORAGE_KEY = 'dyndisplay-theme'

function applyTheme(light) {
  document.documentElement.classList.toggle('light', light)
  try {
    localStorage.setItem(STORAGE_KEY, light ? 'light' : 'dark')
  } catch (e) {}
}

export default function ThemeToggle({ className = '' }) {
  const [light, setLight] = useState(() => document.documentElement.classList.contains('light'))

  useEffect(() => {
    applyTheme(light)
  }, [light])

  return (
    <button
      onClick={() => setLight(prev => !prev)}
      className={`theme-toggle flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-[#1a1f24] text-[#a0a7b3] hover:text-white border border-white/10 text-xs transition-all cursor-pointer ${className}`}
      title={light ? 'Activer le thème sombre' : 'Activer le thème clair'}
    >
      {light ? <Moon className="w-3.5 h-3.5" /> : <Sun className="w-3.5 h-3.5" />}
      <span className="font-medium">{light ? 'Sombre' : 'Clair'}</span>
    </button>
  )
}