"use client";
import { createContext, useContext, useEffect, useState } from "react";

type Theme = "light" | "dark" | "mercury";

const ThemeContext = createContext<{
  theme: Theme;
  setTheme: (t: Theme) => void;
}>({ theme: "light", setTheme: () => {} });

export function useTheme() {
  return useContext(ThemeContext);
}

export function ThemeProvider({ children }: { children: React.ReactNode }) {
  const [theme, setTheme] = useState<Theme>("light");

  useEffect(() => {
    const saved = localStorage.getItem("mr-theme") as Theme | null;
    if (saved && ["light", "dark", "mercury"].includes(saved)) {
      setTheme(saved);
    }
  }, []);

  useEffect(() => {
    localStorage.setItem("mr-theme", theme);
    document.documentElement.setAttribute("data-theme", theme);
    // Apply body classes
    document.body.classList.remove("theme-light", "theme-dark", "theme-mercury");
    document.body.classList.add(`theme-${theme}`);
  }, [theme]);

  return (
    <ThemeContext.Provider value={{ theme, setTheme }}>
      {children}
    </ThemeContext.Provider>
  );
}

export function ThemeSwitcher() {
  const { theme, setTheme } = useTheme();

  const themes: { key: Theme; label: string; icon: string; desc: string }[] = [
    { key: "light", label: "Light", icon: "☀️", desc: "Default" },
    { key: "dark", label: "Dark", icon: "🌙", desc: "Easy on eyes" },
    { key: "mercury", label: "Mercury", icon: "☿", desc: "Neon retro-future" },
  ];

  return (
    <div className="flex gap-1">
      {themes.map(t => (
        <button key={t.key} onClick={() => setTheme(t.key)} title={t.desc}
          className={`text-xs px-2 py-1 rounded-md transition-all ${
            theme === t.key
              ? t.key === "mercury"
                ? "bg-fuchsia-600 text-white shadow-lg shadow-fuchsia-500/30"
                : t.key === "dark"
                  ? "bg-slate-800 text-white"
                  : "bg-white text-slate-900 border border-slate-300"
              : "text-slate-400 hover:text-slate-600"
          }`}>
          {t.icon}
        </button>
      ))}
    </div>
  );
}
