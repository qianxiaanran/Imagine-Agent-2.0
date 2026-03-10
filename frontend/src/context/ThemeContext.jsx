import React, { useState, useEffect } from 'react';
import { ThemeContext } from './themeContextValue';

export const ThemeProvider = ({ children }) => {
  const [theme, setThemeState] = useState(() => {
  const saved = localStorage.getItem('app_theme');
  return saved === 'light' || saved === 'dark' ? saved : 'system';
});


  const [currentTheme, setCurrentTheme] = useState('light');

  useEffect(() => {
    const root = window.document.documentElement;
    const mediaQuery = window.matchMedia('(prefers-color-scheme: dark)');

    const applyTheme = () => {
      const systemIsDark = mediaQuery.matches;
      let effectiveTheme = theme;
      if (theme === 'system') effectiveTheme = systemIsDark ? 'dark' : 'light';

      root.classList.remove('light', 'dark');
      root.classList.add(effectiveTheme);
      setCurrentTheme(effectiveTheme);
    };

    applyTheme();
    const handleChange = () => { if (theme === 'system') applyTheme(); };
    mediaQuery.addEventListener('change', handleChange);
    return () => mediaQuery.removeEventListener('change', handleChange);
  }, [theme]);

  const setTheme = (newTheme) => {
    localStorage.setItem('app_theme', newTheme);
    setThemeState(newTheme);
  };

  const toggleTheme = () => {
    if (theme === 'system') {
      const systemIsDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
      setTheme(systemIsDark ? 'light' : 'dark');
    } else {
      setTheme(theme === 'dark' ? 'light' : 'dark');
    }
  };

  return (
    <ThemeContext.Provider value={{ theme, setTheme, currentTheme, toggleTheme }}>
      {children}
    </ThemeContext.Provider>
  );
};
export default ThemeProvider;
