import React, { useState, useEffect, useRef } from 'react';
import { Eye, EyeOff, Loader2, MessageCircle, ArrowLeft } from 'lucide-react';
import Button from '../../components/Button';
import authApi from '../../api/auth';
import { AUTH_TOKEN_KEY } from '../../api/apiClient';
import { supabase } from '../../api/supabaseClient';

const LoginModal = ({ isOpen, onClose, onSwitchToRegister, onLoginSuccess }) => {
  const REMEMBER_UNTIL_KEY = 'app_auth_remember_until';
  const REMEMBER_WINDOW_MS = 14 * 24 * 60 * 60 * 1000;
  // view states: 'password', 'code_step1', 'code_step2', 'forgot_password'
  const [view, setView] = useState('password');
  const [showPassword, setShowPassword] = useState(false);
  const [formData, setFormData] = useState({ account: '', password: '', code: '' });
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState('');
  const [countdown, setCountdown] = useState(0);
  const [rememberLogin, setRememberLogin] = useState(false);
  const modalRef = useRef(null);

  useEffect(() => {
    let timer;
    if (countdown > 0) {
      timer = setTimeout(() => setCountdown(countdown - 1), 1000);
    }
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
      // Reset state on open
      setView('password');
      setFormData({ account: '', password: '', code: '' });
      setError('');
      setRememberLogin(false);
    }
    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
      document.body.style.overflow = 'unset';
    };
  }, [isOpen, onClose]);

  // Handle password login
  const handlePasswordLogin = async () => {
    if (!formData.account || !formData.password) { setError('请输入账号和密码'); return; }
    setIsLoading(true);
    setError('');
    try {
      const result = await authApi.login(formData.account, formData.password);
      if (result.success) {
        if (result.token) localStorage.setItem(AUTH_TOKEN_KEY, result.token);
        if (rememberLogin) {
          const rememberUntil = Date.now() + REMEMBER_WINDOW_MS;
          localStorage.setItem(REMEMBER_UNTIL_KEY, String(rememberUntil));
          if (result.refresh_token) {
            const { error: sessionError } = await supabase.auth.setSession({
              access_token: result.token,
              refresh_token: result.refresh_token,
            });
            if (sessionError) {
              console.warn('Remember login session error:', sessionError);
              localStorage.removeItem(REMEMBER_UNTIL_KEY);
            }
          } else {
            console.warn('Remember login requested but refresh token missing.');
            localStorage.removeItem(REMEMBER_UNTIL_KEY);
          }
        } else {
          localStorage.removeItem(REMEMBER_UNTIL_KEY);
          await supabase.auth.signOut();
        }
        onLoginSuccess();
      } else { setError('登录失败，请检查凭证'); }
    } catch (err) { setError('请检查您的账号或密码是否正确'); } finally { setIsLoading(false); }
  };

  // Handle sending code for Login flow
  const handleSendCode = async () => {
    if (!formData.account) { setError('请输入手机号'); return; }
    setIsLoading(true);
    setError('');
    try {
      await authApi.sendCode(formData.account);
      setCountdown(60);
      setView('code_step2');
    } catch (err) { setError('验证码发送失败，请重试'); } finally { setIsLoading(false); }
  };

  // Handle sending code for Reset Password flow
  const handleSendResetCode = async () => {
    if (!formData.account) { setError('请输入手机号'); return; }
    if (countdown > 0) return;
    setIsLoading(true);
    setError('');
    try {
      await authApi.sendCode(formData.account);
      setCountdown(60);
      alert('验证码已发送');
    } catch (err) { setError('验证码发送失败，请重试'); } finally { setIsLoading(false); }
  };

  // Handle code login
  const handleCodeLogin = async () => {
    if (!formData.code) { setError('请输入验证码'); return; }
    setIsLoading(true);
    setError('');
    try {
      const result = await authApi.loginWithCode(formData.account, formData.code);
      if (result.success) {
        if (result.token) localStorage.setItem(AUTH_TOKEN_KEY, result.token);
        localStorage.removeItem(REMEMBER_UNTIL_KEY);
        await supabase.auth.signOut();
        onLoginSuccess();
      } else { setError('验证码错误或过期'); }
    } catch (err) { setError('登录失败'); } finally { setIsLoading(false); }
  };

  // Handle Password Reset
  const handleResetPassword = async () => {
    if (!formData.account || !formData.code || !formData.password) {
      setError('请填写完整信息'); return;
    }
    setIsLoading(true);
    setError('');
    try {
      await authApi.resetPassword(formData.account, formData.code, formData.password);
      alert('密码重置成功，请使用新密码登录');
      // Reset form and go back to password login
      setFormData(prev => ({ ...prev, password: '', code: '' }));
      setView('password');
    } catch (err) {
      setError('重置失败：' + (err.response?.data?.detail || '验证码错误或服务异常'));
    } finally {
      setIsLoading(false);
    }
  };

  const commonFooter = (
    <>
      <div className="mt-10 mb-6 relative flex items-center justify-center">
        <div className="absolute inset-0 flex items-center"><div className="w-full border-t border-gray-100 dark:border-gray-800"></div></div>
        <span className="relative bg-white dark:bg-gray-900 px-4 text-xs text-gray-300 dark:text-gray-600">其他登录方式</span>
      </div>
      <div className="flex justify-center mb-8">
        <button className="w-10 h-10 rounded-full bg-[#00c250] flex items-center justify-center text-white hover:opacity-90 transition-opacity"><MessageCircle fill="white" size={20} className="transform -scale-x-100" /></button>
      </div>
      <div className="text-center">
        <p className="text-[10px] text-gray-400">点击继续 代表你同意 <a href="#" className="underline hover:text-gray-600">用户协议</a> 和 <a href="#" className="underline hover:text-gray-600">隐私政策</a></p>
      </div>
    </>
  );

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center p-4 animate-in fade-in duration-200">
      <div className="absolute inset-0 bg-black/40 backdrop-blur-sm"></div>
      <div ref={modalRef} className="relative bg-white dark:bg-gray-900 rounded-xl shadow-2xl w-full max-w-[420px] p-10 animate-in zoom-in-95 duration-200 border border-gray-100 dark:border-gray-800">

        {/* View: Password Login */}
        {view === 'password' && (
          <>
            <div className="text-center mb-10">
              <h1 className="text-2xl font-bold text-gray-800 dark:text-white flex items-center justify-center gap-2">欢迎来到 imagine Agent2.0</h1>
            </div>
            <div className="space-y-4">
              <div className="relative group">
                <input type="text" placeholder="手机号/邮箱" className="w-full bg-[#f5f5f5] dark:bg-gray-800 text-gray-900 dark:text-white px-4 py-3 rounded-lg outline-none border border-transparent focus:bg-white dark:focus:bg-gray-800 focus:border-gray-200 dark:focus:border-gray-600 focus:ring-2 focus:ring-gray-100 dark:focus:ring-gray-700 transition-all placeholder:text-gray-400 text-[15px]" value={formData.account} onChange={(e) => setFormData({...formData, account: e.target.value})} />
              </div>
              <div className="relative group">
                <input type={showPassword ? "text" : "password"} placeholder="密码" className="w-full bg-[#f5f5f5] dark:bg-gray-800 text-gray-900 dark:text-white px-4 py-3 rounded-lg outline-none border border-transparent focus:bg-white dark:focus:bg-gray-800 focus:border-gray-200 dark:focus:border-gray-600 focus:ring-2 focus:ring-gray-100 dark:focus:ring-gray-700 transition-all placeholder:text-gray-400 text-[15px]" value={formData.password} onChange={(e) => setFormData({...formData, password: e.target.value})} />
                <button className="absolute right-4 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600 transition-colors" onClick={() => setShowPassword(!showPassword)}>{showPassword ? <Eye size={18} /> : <EyeOff size={18} />}</button>
              </div>
              {error && <div className="text-red-500 text-xs text-center">{error}</div>}
              <div className="flex items-center justify-between">
                <button
                  type="button"
                  className={`inline-flex items-center gap-2 px-3 py-1.5 rounded-full border text-xs font-medium transition-colors ${
                    rememberLogin
                      ? 'bg-black text-white border-black'
                      : 'bg-white dark:bg-gray-800 text-gray-600 dark:text-gray-300 border-gray-200 dark:border-gray-700 hover:border-gray-400'
                  }`}
                  onClick={() => setRememberLogin((prev) => !prev)}
                >
                  <span className={`inline-block w-2 h-2 rounded-full ${rememberLogin ? 'bg-emerald-400' : 'bg-gray-300'}`}></span>
                  两周内免登录
                </button>
                <button className="text-gray-400 text-xs hover:text-gray-600 dark:hover:text-gray-300 transition-colors" onClick={() => { setView('forgot_password'); setError(''); }}>忘记密码?</button>
              </div>
              <div className="space-y-3 pt-2">
                <Button variant="loginBlack" className="w-full font-bold" onClick={handlePasswordLogin} isLoading={isLoading}>登录</Button>
                <Button variant="loginOutline" className="w-full" onClick={() => { setView('code_step1'); setError(''); }}>使用验证码登录</Button>
              </div>
              <div className="text-center pt-2">
                <button className="text-gray-500 hover:text-gray-900 dark:hover:text-white text-sm transition-colors" onClick={onSwitchToRegister}>注册账号</button>
              </div>
            </div>
          </>
        )}

        {/* View: Forgot Password */}
        {view === 'forgot_password' && (
          <>
            <div className="mb-8">
              <button onClick={() => { setView('password'); setError(''); }} className="flex items-center text-gray-500 hover:text-gray-900 dark:hover:text-white transition-colors mb-4">
                <ArrowLeft size={16} className="mr-1" /> 返回登录
              </button>
              <h1 className="text-2xl font-bold text-gray-800 dark:text-white text-center">重置密码</h1>
            </div>

            <div className="space-y-4">
              {/* Phone Input */}
              <div className="relative group">
                <input type="text" placeholder="请输入手机号" className="w-full bg-[#f5f5f5] dark:bg-gray-800 text-gray-900 dark:text-white px-4 py-3 rounded-lg outline-none border border-transparent focus:bg-white dark:focus:bg-gray-800 focus:border-gray-200 dark:focus:border-gray-600 focus:ring-2 focus:ring-gray-100 dark:focus:ring-gray-700 transition-all placeholder:text-gray-400 text-[15px]" value={formData.account} onChange={(e) => setFormData({...formData, account: e.target.value})} />
              </div>

              {/* Code Input with Send Button */}
              <div className="relative group flex gap-3">
                <input type="text" placeholder="验证码" className="flex-1 bg-[#f5f5f5] dark:bg-gray-800 text-gray-900 dark:text-white px-4 py-3 rounded-lg outline-none border border-transparent focus:bg-white dark:focus:bg-gray-800 focus:border-gray-200 dark:focus:border-gray-600 focus:ring-2 focus:ring-gray-100 dark:focus:ring-gray-700 transition-all placeholder:text-gray-400 text-[15px]" value={formData.code} onChange={(e) => setFormData({...formData, code: e.target.value})} />
                <button className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors min-w-[100px] ${countdown > 0 ? 'bg-gray-100 dark:bg-gray-800 text-gray-400 cursor-not-allowed' : 'bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 text-gray-600 dark:text-gray-300 hover:text-gray-900 dark:hover:text-white hover:border-gray-400'}`} onClick={handleSendResetCode} disabled={countdown > 0}>{countdown > 0 ? `${countdown}s` : '获取验证码'}</button>
              </div>

              {/* New Password Input */}
              <div className="relative group">
                <input type={showPassword ? "text" : "password"} placeholder="新密码" className="w-full bg-[#f5f5f5] dark:bg-gray-800 text-gray-900 dark:text-white px-4 py-3 rounded-lg outline-none border border-transparent focus:bg-white dark:focus:bg-gray-800 focus:border-gray-200 dark:focus:border-gray-600 focus:ring-2 focus:ring-gray-100 dark:focus:ring-gray-700 transition-all placeholder:text-gray-400 text-[15px]" value={formData.password} onChange={(e) => setFormData({...formData, password: e.target.value})} />
                <button className="absolute right-4 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600 transition-colors" onClick={() => setShowPassword(!showPassword)}>{showPassword ? <Eye size={18} /> : <EyeOff size={18} />}</button>
              </div>
              <div className="text-[11px] text-gray-400 leading-tight px-1">6-16位密码，需包含数字、英文大写字母和小写字母</div>

              {error && <div className="text-red-500 text-xs text-center">{error}</div>}

              <div className="space-y-3 pt-4">
                <Button variant="loginBlack" className="w-full font-bold" onClick={handleResetPassword} isLoading={isLoading}>重置密码并登录</Button>
              </div>
            </div>
          </>
        )}

        {/* View: Code Login Step 1 (Input Phone) */}
        {view === 'code_step1' && (
          <>
            <div className="text-center mb-10">
              <h1 className="text-2xl font-bold text-gray-800 dark:text-white flex items-center justify-center gap-2">欢迎来到 FlowUs</h1>
            </div>
            <div className="space-y-4">
              <div className="relative group">
                <input type="text" placeholder="请输入手机号" className="w-full bg-[#f5f5f5] dark:bg-gray-800 text-gray-900 dark:text-white px-4 py-3 rounded-lg outline-none border border-transparent focus:bg-white dark:focus:bg-gray-800 focus:border-gray-200 dark:focus:border-gray-600 focus:ring-2 focus:ring-gray-100 dark:focus:ring-gray-700 transition-all placeholder:text-gray-400 text-[15px]" value={formData.account} onChange={(e) => setFormData({...formData, account: e.target.value})} />
              </div>
              {error && <div className="text-red-500 text-xs text-center">{error}</div>}
              <div className="space-y-3 pt-4">
                <Button variant="loginBlack" className="w-full font-bold" onClick={handleSendCode} isLoading={isLoading}>继续</Button>
                <Button variant="loginOutline" className="w-full" onClick={() => { setView('password'); setError(''); }}>使用密码登录</Button>
              </div>
              <div className="text-center pt-2">
                <button className="text-gray-500 hover:text-gray-900 dark:hover:text-white text-sm transition-colors" onClick={onSwitchToRegister}>注册账号</button>
              </div>
            </div>
          </>
        )}

        {/* View: Code Login Step 2 (Input Code) */}
        {view === 'code_step2' && (
          <>
             <div className="text-center mb-10">
              <h1 className="text-2xl font-bold text-gray-800 dark:text-white flex items-center justify-center gap-2">欢迎回来</h1>
            </div>
            <div className="space-y-4">
              <div className="relative group">
                <input type="text" disabled className="w-full bg-[#f5f5f5] dark:bg-gray-800 text-gray-500 px-4 py-3 rounded-lg outline-none border border-transparent text-[15px] cursor-not-allowed" value={formData.account} />
              </div>
              <div className="relative group">
                <input type="text" placeholder="请输入验证码" className="w-full bg-[#f5f5f5] dark:bg-gray-800 text-gray-900 dark:text-white px-4 py-3 rounded-lg outline-none border border-transparent focus:bg-white dark:focus:bg-gray-800 focus:border-gray-200 dark:focus:border-gray-600 focus:ring-2 focus:ring-gray-100 dark:focus:ring-gray-700 transition-all placeholder:text-gray-300 text-[15px]" value={formData.code} onChange={(e) => setFormData({...formData, code: e.target.value})} />
                <div className="absolute right-4 top-1/2 -translate-y-1/2 text-gray-400 text-sm">
                   倒计时 {countdown}s
                </div>
              </div>
              {error && <div className="text-red-500 text-xs text-center">{error}</div>}
              <div className="space-y-3 pt-4">
                <button className={`w-full rounded-lg py-3 font-bold text-[15px] transition-colors ${formData.code ? 'bg-black text-white hover:bg-gray-800 dark:bg-white dark:text-black dark:hover:bg-gray-200 shadow-lg' : 'bg-[#bfbfbf] dark:bg-gray-700 text-white cursor-not-allowed'}`} onClick={handleCodeLogin} disabled={!formData.code || isLoading}>
                    {isLoading ? <Loader2 size={18} className="animate-spin inline mr-2" /> : null}
                    登录
                </button>
                <Button variant="loginOutline" className="w-full" onClick={() => { setView('password'); setError(''); }}>使用密码登录</Button>
              </div>
              <div className="text-center pt-2">
                 <button className="text-gray-500 hover:text-gray-900 dark:hover:text-white text-sm transition-colors" onClick={onSwitchToRegister}>注册账号</button>
              </div>
            </div>
          </>
        )}

        {/* Only show footer on Login/Register default views, hide on Forgot Password to keep it clean, or keep it. I'll hide it for Forgot Password for cleaner UI */}
        {view !== 'forgot_password' && commonFooter}
      </div>
    </div>
  );
};

export default LoginModal;
