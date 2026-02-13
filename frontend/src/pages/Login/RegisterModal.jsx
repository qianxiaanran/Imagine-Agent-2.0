import React, { useState, useEffect, useRef } from 'react';
import { PartyPopper, Eye, EyeOff } from 'lucide-react';
import Button from '../../components/Button';
import authApi from '../../api/auth';
import { AUTH_TOKEN_KEY } from '../../api/apiClient';

const RegisterModal = ({ isOpen, onClose, onSwitchToLogin, onRegisterSuccess }) => {
  const [showPassword, setShowPassword] = useState(false);
  const [formData, setFormData] = useState({ account: '', code: '', password: '' });
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState('');
  const [countdown, setCountdown] = useState(0);
  const modalRef = useRef(null);

  const extractReason = (err, fallback) => {
    const msg = err?.message || fallback;
    return typeof msg === 'string' && msg.trim() ? msg : fallback;
  };

  const isFormFilled = formData.account && formData.code && formData.password;

  useEffect(() => {
    let timer;
    if (countdown > 0) timer = setTimeout(() => setCountdown(countdown - 1), 1000);
    return () => clearTimeout(timer);
  }, [countdown]);

  useEffect(() => {
    const handleClickOutside = (event) => {
      if (modalRef.current && !modalRef.current.contains(event.target)) {
        onClose();
      }
    };

    if (isOpen) {
      document.addEventListener('mousedown', handleClickOutside);
      document.body.style.overflow = 'hidden';
      setError('');
      setCountdown(0);
    }

    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
      document.body.style.overflow = 'unset';
    };
  }, [isOpen, onClose]);

  const handleSendCode = async () => {
    if (!formData.account) {
      setError('请输入手机号/邮箱');
      return;
    }
    if (countdown > 0) return;

    try {
      await authApi.sendCode(formData.account);
      setCountdown(60);
      setError('');
      alert('验证码已发送，请查收');
    } catch (err) {
      setError(`验证码发送失败：${extractReason(err, '请稍后重试')}`);
    }
  };

  const handleRegister = async () => {
    if (!formData.account || !formData.code || !formData.password) {
      setError('请填写完整信息');
      return;
    }

    setIsLoading(true);
    setError('');
    try {
      const result = await authApi.register(formData.account, formData.password, formData.code);
      if (result.success) {
        if (result.token) {
          localStorage.setItem(AUTH_TOKEN_KEY, result.token);
        }
        onRegisterSuccess();
      } else {
        setError('注册失败：请检查输入信息后重试');
      }
    } catch (err) {
      setError(`注册失败：${extractReason(err, '服务暂不可用')}`);
      console.error(err);
    } finally {
      setIsLoading(false);
    }
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center p-4 animate-in fade-in duration-200">
      <div className="absolute inset-0 bg-black/40 backdrop-blur-sm"></div>
      <div ref={modalRef} className="relative bg-white dark:bg-gray-900 rounded-xl shadow-2xl w-full max-w-[420px] p-10 animate-in zoom-in-95 duration-200 border border-gray-100 dark:border-gray-800">
        <div className="text-center mb-8">
          <h1 className="text-2xl font-bold text-gray-800 dark:text-white flex items-center justify-center gap-2">
            <PartyPopper size={28} className="text-yellow-500" /> 欢迎加入
          </h1>
        </div>

        <div className="space-y-4">
          <div className="relative group">
            <input
              type="text"
              placeholder="请输入手机号/邮箱"
              className="w-full bg-[#f5f5f5] dark:bg-gray-800 text-gray-900 dark:text-white px-4 py-3 rounded-lg outline-none border border-transparent focus:bg-white dark:focus:bg-gray-800 focus:border-gray-200 dark:focus:border-gray-600 focus:ring-2 focus:ring-gray-100 dark:focus:ring-gray-700 transition-all placeholder:text-gray-400 text-[15px]"
              value={formData.account}
              onChange={(e) => setFormData({ ...formData, account: e.target.value })}
            />
          </div>

          <div className="relative group flex gap-3">
            <input
              type="text"
              placeholder="请输入验证码"
              className="flex-1 bg-[#f5f5f5] dark:bg-gray-800 text-gray-900 dark:text-white px-4 py-3 rounded-lg outline-none border border-transparent focus:bg-white dark:focus:bg-gray-800 focus:border-gray-200 dark:focus:border-gray-600 focus:ring-2 focus:ring-gray-100 dark:focus:ring-gray-700 transition-all placeholder:text-gray-400 text-[15px]"
              value={formData.code}
              onChange={(e) => setFormData({ ...formData, code: e.target.value })}
            />
            <button
              className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors min-w-[100px] ${countdown > 0 ? 'bg-gray-100 dark:bg-gray-800 text-gray-400 cursor-not-allowed' : 'bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 text-gray-600 dark:text-gray-300 hover:text-gray-900 dark:hover:text-white hover:border-gray-400'}`}
              onClick={handleSendCode}
              disabled={countdown > 0}
            >
              {countdown > 0 ? `倒计时 ${countdown}s` : '获取验证码'}
            </button>
          </div>

          <div className="relative group">
            <input
              type={showPassword ? 'text' : 'password'}
              placeholder="请输入密码"
              className="w-full bg-[#f5f5f5] dark:bg-gray-800 text-gray-900 dark:text-white px-4 py-3 rounded-lg outline-none border border-transparent focus:bg-white dark:focus:bg-gray-800 focus:border-gray-200 dark:focus:border-gray-600 focus:ring-2 focus:ring-gray-100 dark:focus:ring-gray-700 transition-all placeholder:text-gray-400 text-[15px]"
              value={formData.password}
              onChange={(e) => setFormData({ ...formData, password: e.target.value })}
            />
            <button
              className="absolute right-4 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600 transition-colors"
              onClick={() => setShowPassword(!showPassword)}
              type="button"
            >
              {showPassword ? <Eye size={18} /> : <EyeOff size={18} />}
            </button>
          </div>

          <div className="text-[11px] text-gray-400 leading-tight px-1">建议使用 6-16 位包含字母和数字的密码</div>

          {error && <div className="text-red-500 text-xs text-center">{error}</div>}

          <div className="space-y-3 pt-2">
            <Button
              variant="loginPrimary"
              className={`w-full font-bold transition-colors duration-200 ${
                isFormFilled
                  ? '!bg-black !text-white hover:!bg-gray-800 dark:!bg-white dark:!text-black'
                  : '!bg-gray-300 !text-white cursor-not-allowed'
              }`}
              onClick={handleRegister}
              isLoading={isLoading}
            >
              继续
            </Button>
          </div>

          <div className="text-center pt-2">
            <button className="text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 text-sm transition-colors" onClick={onSwitchToLogin} type="button">
              返回登录页
            </button>
          </div>
        </div>

        <div className="mt-10 text-center">
          <p className="text-[10px] text-gray-400">点击继续 代表你同意 <a href="#" className="underline hover:text-gray-600">用户协议</a> 和 <a href="#" className="underline hover:text-gray-600">隐私政策</a></p>
        </div>
      </div>
    </div>
  );
};

export default RegisterModal;
