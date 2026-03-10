import { createContext, useContext } from 'react';

export const ThemeContext = createContext({
  theme: 'system',
  setTheme: () => {},
  currentTheme: 'light',
  toggleTheme: () => {},
});

export const useTheme = () => useContext(ThemeContext);
