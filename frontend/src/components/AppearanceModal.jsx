import React from 'react';
import { X, Sun, Moon, Monitor } from 'lucide-react';
// 依赖 Context 模块
import { useTheme } from '../context/themeContextValue';

const AppearanceModal = ({ isOpen, onClose }) => {
  // 如果尚未创建 ThemeContext，这个 hook 可能会报错，确保后续创建 context 文件
  const { theme, setTheme } = useTheme();

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center p-4 animate-in fade-in duration-200">
      <div className="absolute inset-0 bg-black/40 backdrop-blur-sm" onClick={onClose}></div>
      <div className="relative bg-white dark:bg-gray-900 rounded-xl shadow-2xl w-full max-w-[400px] p-6 animate-in zoom-in-95 duration-200 border border-gray-200 dark:border-gray-700">
        <div className="flex items-center justify-between mb-6">
           <h2 className="text-xl font-bold text-gray-900 dark:text-white">外观设置</h2>
           <button onClick={onClose} className="p-1 rounded-full hover:bg-gray-100 dark:hover:bg-gray-800 text-gray-500 dark:text-gray-400"><X size={20}/></button>
        </div>

        <div className="space-y-4">
            <label className={`flex items-center justify-between p-4 rounded-xl border cursor-pointer transition-all ${theme === 'light' ? 'border-blue-500 bg-blue-50 dark:bg-blue-900/20' : 'border-gray-200 dark:border-gray-700 hover:border-gray-300 dark:hover:border-gray-600'}`}>
                <div className="flex items-center gap-3">
                    <div className="w-8 h-8 rounded-full bg-gray-100 flex items-center justify-center text-orange-500"><Sun size={18} /></div>
                    <span className="font-medium text-gray-900 dark:text-white">浅色模式</span>
                </div>
                <input type="radio" name="theme" checked={theme === 'light'} onChange={() => setTheme('light')} className="w-4 h-4 text-blue-600" />
            </label>

            <label className={`flex items-center justify-between p-4 rounded-xl border cursor-pointer transition-all ${theme === 'dark' ? 'border-blue-500 bg-blue-50 dark:bg-blue-900/20' : 'border-gray-200 dark:border-gray-700 hover:border-gray-300 dark:hover:border-gray-600'}`}>
                <div className="flex items-center gap-3">
                    <div className="w-8 h-8 rounded-full bg-gray-800 flex items-center justify-center text-blue-300"><Moon size={18} /></div>
                    <span className="font-medium text-gray-900 dark:text-white">深色模式</span>
                </div>
                <input type="radio" name="theme" checked={theme === 'dark'} onChange={() => setTheme('dark')} className="w-4 h-4 text-blue-600" />
            </label>

            <label className={`flex items-center justify-between p-4 rounded-xl border cursor-pointer transition-all ${theme === 'system' ? 'border-blue-500 bg-blue-50 dark:bg-blue-900/20' : 'border-gray-200 dark:border-gray-700 hover:border-gray-300 dark:hover:border-gray-600'}`}>
                <div className="flex items-center gap-3">
                    <div className="w-8 h-8 rounded-full bg-gray-200 dark:bg-gray-700 flex items-center justify-center text-gray-600 dark:text-gray-300"><Monitor size={18} /></div>
                    <span className="font-medium text-gray-900 dark:text-white">跟随系统</span>
                </div>
                <input type="radio" name="theme" checked={theme === 'system'} onChange={() => setTheme('system')} className="w-4 h-4 text-blue-600" />
            </label>
        </div>
      </div>
    </div>
  );
};

export default AppearanceModal;
