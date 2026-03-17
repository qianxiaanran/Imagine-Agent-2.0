import React, { useEffect, useRef, useState } from 'react';
import { Eye, EyeOff } from 'lucide-react';
import authApi from '../../api/auth';
import { AUTH_REFRESH_TOKEN_KEY, AUTH_TOKEN_KEY } from '../../api/config';
import AuthHoverButton from './AuthHoverButton';
import {
  AuthModalShell,
  Field,
  InfoDialog,
  SectionHeader,
  secondaryButtonClassName,
} from './AuthModalShared';

const codeButtonClassName = 'min-w-[112px] rounded-2xl px-4 py-3 text-sm font-medium transition-colors';

const RegisterModal = ({ isOpen, onClose, onSwitchToLogin, onRegisterSuccess }) => {
  const [showPassword, setShowPassword] = useState(false);
  const [formData, setFormData] = useState({ account: '', code: '', password: '' });
  const [isLoading, setIsLoading] = useState(false);
  const [isSendingCode, setIsSendingCode] = useState(false);
  const [error, setError] = useState('');
  const [countdown, setCountdown] = useState(0);
  const [isLegalTipOpen, setIsLegalTipOpen] = useState(false);
  const [isTyping, setIsTyping] = useState(false);
  const modalRef = useRef(null);

  const extractReason = (err, fallback) => {
    const msg = err?.message || fallback;
    return typeof msg === 'string' && msg.trim() ? msg : fallback;
  };

  const isFormFilled = formData.account && formData.code && formData.password;

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
      setShowPassword(false);
      setFormData({ account: '', code: '', password: '' });
      setError('');
      setCountdown(0);
      setIsLegalTipOpen(false);
      setIsTyping(false);
    }

    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
    };
  }, [isOpen, onClose]);

  const handleSendCode = async () => {
    if (!formData.account) {
      setError('请输入手机号/邮箱');
      return;
    }
    if (countdown > 0 || isSendingCode) return;

    setIsSendingCode(true);
    setError('');

    try {
      await authApi.sendCode(formData.account);
      setCountdown(60);
      alert('验证码已发送，请查收');
    } catch (err) {
      setError(`验证码发送失败：${extractReason(err, '请稍后重试')}`);
    } finally {
      setIsSendingCode(false);
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
      if (!result.success) {
        setError('注册失败：请检查输入信息后重试');
        return;
      }

      if (result.token) {
        localStorage.setItem(AUTH_TOKEN_KEY, result.token);
      }
      if (result.refresh_token) {
        localStorage.setItem(AUTH_REFRESH_TOKEN_KEY, result.refresh_token);
      } else {
        localStorage.removeItem(AUTH_REFRESH_TOKEN_KEY);
      }

      onRegisterSuccess();
    } catch (err) {
      setError(`注册失败：${extractReason(err, '服务暂不可用')}`);
      console.error(err);
    } finally {
      setIsLoading(false);
    }
  };

  const handleOpenLegalTip = (event) => {
    event.preventDefault();
    setIsLegalTipOpen(true);
  };

  if (!isOpen) return null;

  return (
    <AuthModalShell
      modalRef={modalRef}
      onClose={onClose}
      closeLabel="关闭注册弹窗"
      isTyping={isTyping}
      showPassword={showPassword}
      passwordLength={formData.password.length}
    >
      <SectionHeader
        eyebrow="Create Account"
        title="注册你的智能工作台"
        description="使用手机号创建 imagine Agent 2.0 账号。"
      />

      <div className="space-y-4">
        <Field
          value={formData.account}
          placeholder="手机号/邮箱"
          onChange={(event) => setField('account', event.target.value)}
          onFocus={handleFieldFocus}
          onBlur={handleFieldBlur}
        />

        <div className="flex gap-3">
          <Field
            wrapperClassName="flex-1"
            value={formData.code}
            placeholder="验证码"
            onChange={(event) => setField('code', event.target.value)}
            onFocus={handleFieldFocus}
            onBlur={handleFieldBlur}
          />
          <button
            type="button"
            className={`${codeButtonClassName} ${
              countdown > 0 || isSendingCode
                ? 'cursor-not-allowed bg-slate-100 text-slate-400 dark:bg-slate-800 dark:text-slate-500'
                : 'border border-slate-200 bg-white text-slate-700 hover:border-slate-400 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-200 dark:hover:border-slate-500'
            }`}
            onClick={handleSendCode}
            disabled={countdown > 0 || isSendingCode}
          >
            {isSendingCode ? '发送中...' : countdown > 0 ? `${countdown}s` : '获取验证码'}
          </button>
        </div>

        <Field
          type={showPassword ? 'text' : 'password'}
          value={formData.password}
          placeholder="密码"
          onChange={(event) => setField('password', event.target.value)}
          onFocus={handleFieldFocus}
          onBlur={handleFieldBlur}
          trailing={(
            <button
              type="button"
              className="text-slate-400 hover:text-slate-600 dark:hover:text-slate-300"
              onClick={() => setShowPassword((prev) => !prev)}
            >
              {showPassword ? <Eye size={18} /> : <EyeOff size={18} />}
            </button>
          )}
        />

        <div className="px-1 text-[11px] text-slate-400 dark:text-slate-500">建议使用 6-16 位包含字母和数字的密码</div>

        {error && (
          <div className="rounded-2xl border border-rose-200 bg-rose-50 px-4 py-3 text-xs text-rose-700 dark:border-rose-500/30 dark:bg-rose-500/10 dark:text-rose-200">
            {error}
          </div>
        )}

        <div className="space-y-3 pt-3">
          <AuthHoverButton
            type="button"
            text={isLoading ? '注册中...' : '注册'}
            onClick={handleRegister}
            disabled={!isFormFilled || isLoading}
            animated={false}
            className="h-12 text-base"
          />
          <button type="button" className={secondaryButtonClassName} onClick={onSwitchToLogin}>
            返回登录
          </button>
        </div>

        <div className="pt-2 text-center">
          <button
            type="button"
            className="text-sm font-medium text-slate-500 hover:text-slate-900 dark:hover:text-white"
            onClick={onSwitchToLogin}
          >
            已有账号，去登录
          </button>
        </div>
      </div>

      <div className="mt-10 text-center text-[11px] leading-6 text-slate-400 dark:text-slate-500">
        点击继续代表你同意
        <button type="button" onClick={handleOpenLegalTip} className="ml-1 underline hover:text-slate-600 dark:hover:text-slate-300">
          用户协议
        </button>
        和
        <button type="button" onClick={handleOpenLegalTip} className="ml-1 underline hover:text-slate-600 dark:hover:text-slate-300">
          隐私政策
        </button>
      </div>

      <InfoDialog open={isLegalTipOpen} onClose={() => setIsLegalTipOpen(false)} title="协议占位提示">
        暂时还没想好，只是占个位嘿嘿
      </InfoDialog>
    </AuthModalShell>
  );
};

export default RegisterModal;
