import React, { useEffect, useRef, useState } from 'react';
import { ArrowLeft, Eye, EyeOff, MessageCircle } from 'lucide-react';
import authApi from '../../api/auth';
import {
  AUTH_REFRESH_TOKEN_KEY,
  AUTH_REMEMBER_UNTIL_KEY,
  AUTH_TOKEN_KEY,
} from '../../api/config';
import { supabase } from '../../api/supabaseClient';
import AuthHoverButton from './AuthHoverButton';
import {
  AuthModalShell,
  Field,
  InfoDialog,
  SectionHeader,
  secondaryButtonClassName,
  smallActionClassName,
} from './AuthModalShared';

const RememberChip = ({ active, onToggle }) => (
  <button
    type="button"
    className={`${smallActionClassName} ${
      active
        ? 'border-slate-900 bg-slate-900 text-white dark:border-white dark:bg-white dark:text-slate-900'
        : 'border-slate-200 bg-white text-slate-600 hover:border-slate-400 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-300 dark:hover:border-slate-500'
    }`}
    onClick={onToggle}
  >
    <span className={`inline-block h-2 w-2 rounded-full ${active ? 'bg-emerald-400' : 'bg-slate-300'}`}></span>
    两周内免登录
  </button>
);

const LoginModal = ({ isOpen, onClose, onSwitchToRegister, onLoginSuccess }) => {
  const REMEMBER_WINDOW_MS = 14 * 24 * 60 * 60 * 1000;

  const [view, setView] = useState('password');
  const [showPassword, setShowPassword] = useState(false);
  const [formData, setFormData] = useState({ account: '', password: '', code: '' });
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState('');
  const [showRegisterShortcut, setShowRegisterShortcut] = useState(false);
  const [countdown, setCountdown] = useState(0);
  const [rememberLogin, setRememberLogin] = useState(false);
  const [isWeChatTipOpen, setIsWeChatTipOpen] = useState(false);
  const [isLegalTipOpen, setIsLegalTipOpen] = useState(false);
  const [isTyping, setIsTyping] = useState(false);
  const modalRef = useRef(null);

  const extractReason = (err, fallback) => {
    const msg = err?.message || fallback;
    return typeof msg === 'string' && msg.trim() ? msg : fallback;
  };

  const isUnregisteredReason = (msg = '') =>
    /\u672A\u6CE8\u518C|\u5C1A\u672A\u6CE8\u518C|not registered|not found|unregistered/i.test(String(msg));

  const setField = (key, value) => setFormData((prev) => ({ ...prev, [key]: value }));
  const handleFieldFocus = () => setIsTyping(true);
  const handleFieldBlur = () => setIsTyping(false);

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
      setView('password');
      setFormData({ account: '', password: '', code: '' });
      setError('');
      setShowRegisterShortcut(false);
      setRememberLogin(false);
      setCountdown(0);
      setIsWeChatTipOpen(false);
      setIsLegalTipOpen(false);
      setIsTyping(false);
    }

    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
    };
  }, [isOpen, onClose]);

  const goPasswordView = () => {
    setView('password');
    setError('');
    setShowRegisterShortcut(false);
  };

  const handlePasswordLogin = async () => {
    if (!formData.account || !formData.password) {
      setError('请输入账号和密码');
      return;
    }

    setIsLoading(true);
    setError('');
    setShowRegisterShortcut(false);

    try {
      const result = await authApi.login(formData.account, formData.password);
      if (!result.success) {
        setError('登录失败：账号密码校验未通过');
        return;
      }

      if (result.token) localStorage.setItem(AUTH_TOKEN_KEY, result.token);
      if (result.refresh_token) {
        localStorage.setItem(AUTH_REFRESH_TOKEN_KEY, result.refresh_token);
      } else {
        localStorage.removeItem(AUTH_REFRESH_TOKEN_KEY);
      }

      if (rememberLogin) {
        const rememberUntil = Date.now() + REMEMBER_WINDOW_MS;
        localStorage.setItem(AUTH_REMEMBER_UNTIL_KEY, String(rememberUntil));

        if (result.refresh_token) {
          try {
            const { error: sessionError } = await supabase.auth.setSession({
              access_token: result.token,
              refresh_token: result.refresh_token,
            });
            if (sessionError) console.warn('Remember login session error:', sessionError);
          } catch (e) {
            console.warn('Remember login setSession failed:', e);
          }
        } else {
          localStorage.removeItem(AUTH_REMEMBER_UNTIL_KEY);
        }
      } else {
        localStorage.removeItem(AUTH_REMEMBER_UNTIL_KEY);
        localStorage.removeItem(AUTH_REFRESH_TOKEN_KEY);
        void supabase.auth.signOut().catch((e) => console.warn('Supabase signOut failed:', e));
      }

      onLoginSuccess();
    } catch (err) {
      setError(`登录失败：${extractReason(err, '请检查账号和密码是否正确')}`);
    } finally {
      setIsLoading(false);
    }
  };

  const handleSendCode = async () => {
    if (!formData.account) {
      setError('请输入手机号');
      return;
    }

    setIsLoading(true);
    setError('');
    setShowRegisterShortcut(false);

    try {
      const checkResult = await authApi.checkAccount(formData.account);
      if (!checkResult?.registered) {
        setError('该手机号未注册，请先注册后再登录');
        setShowRegisterShortcut(true);
        return;
      }
      await authApi.sendCode(formData.account);
      setCountdown(60);
      setView('code_step2');
    } catch (err) {
      setError(`验证码发送失败：${extractReason(err, '请稍后重试')}`);
    } finally {
      setIsLoading(false);
    }
  };

  const handleSendResetCode = async () => {
    if (!formData.account) {
      setError('请输入手机号');
      return;
    }
    if (countdown > 0) return;

    setIsLoading(true);
    setError('');

    try {
      await authApi.sendCode(formData.account);
      setCountdown(60);
      alert('验证码已发送，请查收短信');
    } catch (err) {
      setError(`验证码发送失败：${extractReason(err, '请稍后重试')}`);
    } finally {
      setIsLoading(false);
    }
  };

  const handleCodeLogin = async () => {
    if (!formData.code) {
      setError('请输入验证码');
      return;
    }

    setIsLoading(true);
    setError('');
    setShowRegisterShortcut(false);

    try {
      const checkResult = await authApi.checkAccount(formData.account);
      if (!checkResult?.registered) {
        setError('该手机号未注册，请先注册后再登录');
        setShowRegisterShortcut(true);
        return;
      }

      const result = await authApi.loginWithCode(formData.account, formData.code);
      if (!result.success) {
        setError('登录失败：验证码校验未通过');
        return;
      }

      try {
        await supabase.auth.signOut();
      } catch (e) {
        console.warn('Supabase signOut before sms login failed:', e);
      }
      if (result.token) localStorage.setItem(AUTH_TOKEN_KEY, result.token);
      localStorage.removeItem(AUTH_REFRESH_TOKEN_KEY);
      if (rememberLogin) {
        localStorage.setItem(AUTH_REMEMBER_UNTIL_KEY, String(Date.now() + REMEMBER_WINDOW_MS));
      } else {
        localStorage.removeItem(AUTH_REMEMBER_UNTIL_KEY);
      }
      onLoginSuccess();
    } catch (err) {
      const reason = extractReason(err, '验证码登录失败');
      setError(reason);
      setShowRegisterShortcut(isUnregisteredReason(reason));
    } finally {
      setIsLoading(false);
    }
  };

  const handleResetPassword = async () => {
    if (!formData.account || !formData.code || !formData.password) {
      setError('请填写完整信息');
      return;
    }

    setIsLoading(true);
    setError('');

    try {
      await authApi.resetPassword(formData.account, formData.code, formData.password);
      alert('密码重置成功：验证码校验通过，请使用新密码登录');
      setFormData((prev) => ({ ...prev, password: '', code: '' }));
      goPasswordView();
    } catch (err) {
      setError(`重置失败：${extractReason(err, '验证码错误或服务异常')}`);
    } finally {
      setIsLoading(false);
    }
  };

  const handleOpenLegalTip = (event) => {
    event.preventDefault();
    setIsLegalTipOpen(true);
  };

  const renderError = error ? (
    <div className="rounded-2xl border border-rose-200 bg-rose-50 px-4 py-3 text-xs text-rose-700 dark:border-rose-500/30 dark:bg-rose-500/10 dark:text-rose-200">
      {error}
    </div>
  ) : null;

  const renderRegisterShortcut = showRegisterShortcut ? (
    <div className="text-center">
      <button
        type="button"
        onClick={() => {
          setError('');
          setShowRegisterShortcut(false);
          onSwitchToRegister();
        }}
        className="inline-flex items-center rounded-full border border-rose-200 px-3 py-1.5 text-xs font-medium text-rose-600 transition-colors hover:bg-rose-50 dark:border-rose-500/30 dark:text-rose-200 dark:hover:bg-rose-500/10"
      >
        该手机号未注册，去注册
      </button>
    </div>
  ) : null;

  const commonFooter = (
    <>
      <div className="mt-10 mb-6 relative flex items-center justify-center">
        <div className="absolute inset-x-0 border-t border-slate-200 dark:border-slate-800"></div>
        <span className="relative bg-white px-4 text-[11px] text-slate-400 dark:bg-slate-950 dark:text-slate-600">其他登录方式</span>
      </div>
      <div className="flex justify-center">
        <button
          type="button"
          onClick={() => setIsWeChatTipOpen(true)}
          className="flex h-11 w-11 items-center justify-center rounded-full bg-[#00c250] text-white transition-transform hover:-translate-y-0.5 hover:shadow-lg"
        >
          <MessageCircle fill="white" size={20} className="-scale-x-100" />
        </button>
      </div>
      <div className="mt-6 text-center text-[11px] leading-6 text-slate-400 dark:text-slate-500">
        点击继续代表你同意
        <button type="button" onClick={handleOpenLegalTip} className="ml-1 underline hover:text-slate-600 dark:hover:text-slate-300">用户协议</button>
        和
        <button type="button" onClick={handleOpenLegalTip} className="ml-1 underline hover:text-slate-600 dark:hover:text-slate-300">隐私政策</button>
      </div>
    </>
  );

  const renderPasswordView = () => (
    <>
      <SectionHeader
        eyebrow="Welcome Back"
        title="登录你的智能工作台"
        description="继续使用账号密码或短信验证码进入 imagine Agent 2.0。"
      />
      <div className="space-y-4">
        <Field value={formData.account} placeholder="手机号/邮箱" onChange={(event) => setField('account', event.target.value)} onFocus={handleFieldFocus} onBlur={handleFieldBlur} />
        <Field
          type={showPassword ? 'text' : 'password'}
          value={formData.password}
          placeholder="密码"
          onChange={(event) => setField('password', event.target.value)}
          onFocus={handleFieldFocus}
          onBlur={handleFieldBlur}
          trailing={
            <button type="button" className="text-slate-400 hover:text-slate-600 dark:hover:text-slate-300" onClick={() => setShowPassword((prev) => !prev)}>
              {showPassword ? <Eye size={18} /> : <EyeOff size={18} />}
            </button>
          }
        />
        {renderError}
        <div className="flex items-center justify-between gap-3">
          <RememberChip active={rememberLogin} onToggle={() => setRememberLogin((prev) => !prev)} />
          <button type="button" className="text-xs font-medium text-slate-400 hover:text-slate-700 dark:hover:text-slate-300" onClick={() => { setView('forgot_password'); setError(''); setShowRegisterShortcut(false); }}>
            忘记密码？
          </button>
        </div>
        <div className="space-y-3 pt-2">
          <AuthHoverButton type="button" text={isLoading ? '登录中...' : '登录'} onClick={handlePasswordLogin} disabled={isLoading} animated={false} className="h-12 text-base" />
          <button type="button" className={secondaryButtonClassName} onClick={() => { setView('code_step1'); setError(''); setShowRegisterShortcut(false); }}>
            使用验证码登录
          </button>
        </div>
        <div className="pt-2 text-center">
          <button type="button" className="text-sm font-medium text-slate-500 hover:text-slate-900 dark:hover:text-white" onClick={onSwitchToRegister}>
            注册账号
          </button>
        </div>
      </div>
    </>
  );

  const renderForgotPasswordView = () => (
    <>
      <SectionHeader
        eyebrow="Reset Password"
        title="重置密码"
        description="通过验证码校验后，用新密码重新登录。"
        backAction={
          <button type="button" onClick={goPasswordView} className="mb-5 inline-flex items-center gap-1 text-sm font-medium text-slate-500 hover:text-slate-900 dark:hover:text-white">
            <ArrowLeft size={16} /> 返回登录
          </button>
        }
      />
      <div className="space-y-4">
        <Field value={formData.account} placeholder="请输入手机号" onChange={(event) => setField('account', event.target.value)} onFocus={handleFieldFocus} onBlur={handleFieldBlur} />
        <div className="flex gap-3">
          <Field wrapperClassName="flex-1" value={formData.code} placeholder="验证码" onChange={(event) => setField('code', event.target.value)} onFocus={handleFieldFocus} onBlur={handleFieldBlur} />
          <button
            type="button"
            className={`min-w-[112px] rounded-2xl px-4 py-3 text-sm font-medium transition-colors ${countdown > 0 ? 'cursor-not-allowed bg-slate-100 text-slate-400 dark:bg-slate-800 dark:text-slate-500' : 'border border-slate-200 bg-white text-slate-700 hover:border-slate-400 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-200 dark:hover:border-slate-500'}`}
            onClick={handleSendResetCode}
            disabled={countdown > 0}
          >
            {countdown > 0 ? `${countdown}s` : '获取验证码'}
          </button>
        </div>
        <Field
          type={showPassword ? 'text' : 'password'}
          value={formData.password}
          placeholder="新密码"
          onChange={(event) => setField('password', event.target.value)}
          onFocus={handleFieldFocus}
          onBlur={handleFieldBlur}
          trailing={
            <button type="button" className="text-slate-400 hover:text-slate-600 dark:hover:text-slate-300" onClick={() => setShowPassword((prev) => !prev)}>
              {showPassword ? <Eye size={18} /> : <EyeOff size={18} />}
            </button>
          }
        />
        <div className="px-1 text-[11px] text-slate-400 dark:text-slate-500">建议使用 6-16 位包含字母和数字的密码</div>
        {renderError}
        <div className="pt-4">
          <AuthHoverButton type="button" text={isLoading ? '重置中...' : '重置密码并登录'} onClick={handleResetPassword} disabled={isLoading} className="h-12 text-base" />
        </div>
      </div>
    </>
  );

  const renderCodeStepOneView = () => (
    <>
      <SectionHeader eyebrow="SMS Login" title="验证码登录" description="输入手机号后发送验证码，完成一次性登录。" />
      <div className="space-y-4">
        <Field value={formData.account} placeholder="请输入手机号" onChange={(event) => setField('account', event.target.value)} onFocus={handleFieldFocus} onBlur={handleFieldBlur} />
        {renderError}
        {renderRegisterShortcut}
        <div className="space-y-3 pt-4">
          <AuthHoverButton type="button" text={isLoading ? '发送中...' : '继续'} onClick={handleSendCode} disabled={isLoading} className="h-12 text-base" />
          <button type="button" className={secondaryButtonClassName} onClick={goPasswordView}>使用密码登录</button>
        </div>
        <div className="pt-2 text-center">
          <button type="button" className="text-sm font-medium text-slate-500 hover:text-slate-900 dark:hover:text-white" onClick={onSwitchToRegister}>
            注册账号
          </button>
        </div>
      </div>
    </>
  );

  const renderCodeStepTwoView = () => (
    <>
      <SectionHeader eyebrow="Verification" title="输入验证码" description="验证通过后即可直接进入工作台。" />
      <div className="space-y-4">
        <Field value={formData.account} disabled />
        <Field
          value={formData.code}
          placeholder="请输入验证码"
          onChange={(event) => setField('code', event.target.value)}
          onFocus={handleFieldFocus}
          onBlur={handleFieldBlur}
          trailing={<span className="text-sm text-slate-400">{countdown > 0 ? `${countdown}s` : '可重发'}</span>}
        />
        {renderError}
        {renderRegisterShortcut}
        <RememberChip active={rememberLogin} onToggle={() => setRememberLogin((prev) => !prev)} />
        <div className="space-y-3 pt-4">
          <AuthHoverButton type="button" text={isLoading ? '登录中...' : '登录'} onClick={handleCodeLogin} disabled={!formData.code || isLoading} animated={false} className="h-12 text-base" />
          <button type="button" className={secondaryButtonClassName} onClick={goPasswordView}>使用密码登录</button>
        </div>
        <div className="pt-2 text-center">
          <button type="button" className="text-sm font-medium text-slate-500 hover:text-slate-900 dark:hover:text-white" onClick={onSwitchToRegister}>
            注册账号
          </button>
        </div>
      </div>
    </>
  );

  const renderCurrentView = () => {
    if (view === 'forgot_password') return renderForgotPasswordView();
    if (view === 'code_step1') return renderCodeStepOneView();
    if (view === 'code_step2') return renderCodeStepTwoView();
    return renderPasswordView();
  };

  if (!isOpen) return null;

  return (
    <AuthModalShell
      modalRef={modalRef}
      onClose={onClose}
      closeLabel="关闭登录弹窗"
      isTyping={isTyping}
      showPassword={showPassword}
      passwordLength={formData.password.length}
    >
      {renderCurrentView()}
      {view !== 'forgot_password' && commonFooter}

      <InfoDialog open={isWeChatTipOpen} onClose={() => setIsWeChatTipOpen(false)} title="微信登录说明">
        本来想做微信登录的，后期发现开发者认证太麻烦就没做嘿嘿，请使用手机号+验证码或账号密码登录。
      </InfoDialog>
      <InfoDialog open={isLegalTipOpen} onClose={() => setIsLegalTipOpen(false)} title="协议占位提示">
        暂时还没想好，只是占个位嘿嘿
      </InfoDialog>
    </AuthModalShell>
  );
};

export default LoginModal;
