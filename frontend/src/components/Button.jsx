import React from 'react';
import { Loader2 } from 'lucide-react';

const Button = ({
  children,
  variant = 'primary',
  className = '',
  icon: Icon,
  isLoading,
  ...props
}) => {
  const baseStyle = "inline-flex items-center justify-center px-6 py-3 rounded-full font-medium transition-all duration-300 text-sm sm:text-base cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed";

  const variants = {
    primary: "bg-gray-900 text-white hover:bg-black hover:scale-105 hover:shadow-xl shadow-gray-900/20 active:scale-95 dark:bg-white dark:text-black dark:hover:bg-gray-200 dark:shadow-white/10",
    secondary: "bg-gray-100 text-gray-900 hover:bg-gray-200 active:scale-95 dark:bg-gray-800 dark:text-white dark:hover:bg-gray-700",
    outline: "border border-gray-200 text-gray-600 hover:border-gray-900 hover:text-gray-900 bg-white hover:shadow-md active:scale-95 dark:bg-gray-900 dark:border-gray-700 dark:text-gray-400 dark:hover:text-white dark:hover:border-white",
    ghost: "text-gray-500 hover:text-gray-900 hover:bg-gray-50 dark:text-gray-400 dark:hover:text-white dark:hover:bg-gray-800",
    loginPrimary: "bg-[#a3a3a3] text-white hover:bg-[#808080] rounded-lg py-2.5 text-[15px] shadow-none hover:scale-[1.01]",
    loginOutline: "bg-white border border-gray-200 text-gray-700 hover:border-gray-400 hover:text-gray-900 rounded-lg py-2.5 text-[15px] shadow-none hover:scale-[1.01] dark:bg-gray-800 dark:border-gray-700 dark:text-gray-300 dark:hover:border-gray-500",
    loginBlack: "bg-black text-white hover:bg-gray-800 rounded-lg py-3 text-[15px] shadow-lg shadow-black/10 hover:shadow-xl hover:scale-[1.01] active:scale-[0.98] dark:bg-white dark:text-black dark:hover:bg-gray-200",
    loginGrey: "bg-[#f2f2f2] text-gray-400 hover:bg-[#e5e5e5] hover:text-gray-500 rounded-lg py-3 text-[15px] shadow-none cursor-not-allowed dark:bg-gray-700 dark:text-gray-500"
  };

  return (
    <button className={`${baseStyle} ${variants[variant] || variants.primary} ${className}`} disabled={isLoading} {...props}>
      {isLoading ? (
        <Loader2 size={18} className="animate-spin mr-2" />
      ) : (
        Icon && <Icon size={18} className="ml-2 group-hover:translate-x-1 transition-transform" />
      )}
      {children}
    </button>
  );
};

export default Button;