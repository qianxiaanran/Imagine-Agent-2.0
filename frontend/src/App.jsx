import React, { useState, useEffect, Suspense } from 'react';
import ThemeProvider from './context/ThemeContext';
import GlobalStyles from './components/GlobalStyles';
import LoadingScreen from './components/LoadingScreen';
import ErrorBoundary from './components/ErrorBoundary';
import LoginModal from './pages/Login/LoginModal';
import RegisterModal from './pages/Login/RegisterModal';
import { AUTH_TOKEN_KEY } from './api/apiClient';
import { supabase } from './api/supabaseClient';
// 引入 userApi 用于验证 token 有效性
import userApi from './api/user';

// 预加载函数
const loadLandingPage = () => import('./pages/LandingPage');
const loadDashboardPage = () => import('./pages/Dashboard/DashboardPage');
const loadSharedPage = () => import('./pages/Dashboard/SharedChatPage');
const loadAdminPage = () => import('./pages/Admin/AdminPage');

const LandingPage = React.lazy(loadLandingPage);
const DashboardPage = React.lazy(loadDashboardPage);
const SharedChatPage = React.lazy(loadSharedPage);
const AdminPage = React.lazy(loadAdminPage);

export default function App() {
  const [authModalView, setAuthModalView] = useState('closed');
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [currentMode, setCurrentMode] = useState('general');
  const REMEMBER_UNTIL_KEY = 'app_auth_remember_until';

  // 🔒 资源锁状态
  const [isAuthReady, setIsAuthReady] = useState(false);

  // ✨ 路由检测
  const isShareRoute = window.location.pathname.startsWith('/share/');
  const isAdminRoute = window.location.pathname.startsWith('/admin');

  // 只有当所有锁都打开时，才移除 Loading 遮罩
  const shouldShowLoading = !isAuthReady;

  // 1. Auth check

  useEffect(() => {
    const { data } = supabase.auth.onAuthStateChange((_event, session) => {
      const rememberUntil = Number(localStorage.getItem(REMEMBER_UNTIL_KEY) || 0);
      if (!rememberUntil) return;
      if (rememberUntil <= Date.now()) {
        supabase.auth.signOut();
        localStorage.removeItem(REMEMBER_UNTIL_KEY);
        localStorage.removeItem(AUTH_TOKEN_KEY);
        setIsAuthenticated(false);
        return;
      }
      if (session?.access_token) {
        localStorage.setItem(AUTH_TOKEN_KEY, session.access_token);
      } else {
        localStorage.removeItem(AUTH_TOKEN_KEY);
        localStorage.removeItem(REMEMBER_UNTIL_KEY);
      }
    });

    return () => data?.subscription?.unsubscribe();
  }, []);

  // Auth validation & preload
  useEffect(() => {
    // Share route skips auth check
    if (isShareRoute) {
      setIsAuthReady(true);
      loadSharedPage();
      return;
    }

    const checkAuth = async () => {
      let isValidSession = false;
      const settleAuth = () => setIsAuthReady(true);

      try {
        const rememberUntil = Number(localStorage.getItem(REMEMBER_UNTIL_KEY) || 0);
        const hasStoredToken = !!localStorage.getItem(AUTH_TOKEN_KEY);
        const hasAuthHint = rememberUntil > 0 || hasStoredToken;
        if (!hasAuthHint) {
          loadLandingPage();
          settleAuth();
          return;
        }
        if (rememberUntil) {
          if (rememberUntil <= Date.now()) {
            await supabase.auth.signOut();
            localStorage.removeItem(REMEMBER_UNTIL_KEY);
            localStorage.removeItem(AUTH_TOKEN_KEY);
          } else {
            const { data } = await supabase.auth.getSession();
            if (data?.session?.access_token) {
              localStorage.setItem(AUTH_TOKEN_KEY, data.session.access_token);
            } else {
              localStorage.removeItem(REMEMBER_UNTIL_KEY);
            }
          }
        }

        const token = localStorage.getItem(AUTH_TOKEN_KEY);
        if (token) {
          try {
            const profile = await userApi.getProfile();
            if (profile && profile.id && profile.id !== 'anonymous') {
              isValidSession = true;
              setIsAuthenticated(true);
              if (isAdminRoute) {
                loadAdminPage();
              } else {
                loadDashboardPage();
              }
            } else {
              localStorage.removeItem(AUTH_TOKEN_KEY);
            }
          } catch (err) {
            console.warn("Token validation failed:", err);
            localStorage.removeItem(AUTH_TOKEN_KEY);
          }
        }
      } catch (e) {
        console.error("Auth check logic error", e);
      } finally {
        if (!isValidSession) loadLandingPage();
        settleAuth();
      }
    };
    checkAuth();
  }, [isShareRoute, isAdminRoute]);

  // 4. 修复滚动锁定：确保 loading 结束后 body 可以滚动
  useEffect(() => {
    if (shouldShowLoading) {
      document.body.style.overflow = 'hidden';
    } else {
      // 延迟一点点释放，配合淡出动画
      const timer = setTimeout(() => {
        document.body.style.overflow = 'unset';
      }, 100);
      return () => clearTimeout(timer);
    }
    // 清理函数
    return () => { document.body.style.overflow = 'unset'; };
  }, [shouldShowLoading]);

  useEffect(() => {
    const updateAppHeight = () => {
      const height = window.innerHeight || document.documentElement.clientHeight;
      document.documentElement.style.setProperty('--app-height', `${height}px`);
    };
    updateAppHeight();
    window.addEventListener('resize', updateAppHeight);
    window.addEventListener('orientationchange', updateAppHeight);
    return () => {
      window.removeEventListener('resize', updateAppHeight);
      window.removeEventListener('orientationchange', updateAppHeight);
    };
  }, []);

  const handleLoginSuccess = () => { setAuthModalView('closed'); setIsAuthenticated(true); loadDashboardPage(); };
  const handleRegisterSuccess = () => { setAuthModalView('closed'); setIsAuthenticated(true); loadDashboardPage(); };
  const handleLogout = () => {
    localStorage.removeItem(AUTH_TOKEN_KEY);
    localStorage.removeItem(REMEMBER_UNTIL_KEY);
    supabase.auth.signOut();
    setIsAuthenticated(false);
    setCurrentMode('general');
    loadLandingPage();
  };

  return (
    <ErrorBoundary>
      <ThemeProvider>
        <GlobalStyles />

        <div className={`min-h-screen transition-opacity duration-700 ease-in-out ${shouldShowLoading ? 'opacity-0' : 'opacity-100'}`}>
           <Suspense
             fallback={shouldShowLoading ? (
               <div className="min-h-screen bg-white dark:bg-gray-950"></div>
             ) : (
               <LoadingScreen text="正在加载页面..." isVisible />
             )}
           >
             {/* ✨ 路由逻辑分支 */}
             {isShareRoute ? (
               <SharedChatPage />
             ) : (
                 isAuthenticated ? (
                   isAdminRoute ? (
                     <AdminPage />
                   ) : (
                     <DashboardPage
                       onLogout={handleLogout}
                       currentMode={currentMode}
                       onModeChange={setCurrentMode}
                     />
                   )
                 ) : (
                   <LandingPage onOpenLogin={() => setAuthModalView('login')} />
                 )
             )}
           </Suspense>
        </div>

        {/* Loading 遮罩：增加 pointer-events-none 防止在不可见时阻挡鼠标事件 */}
        <div className={`fixed inset-0 z-[9999] transition-opacity duration-500 ${shouldShowLoading ? 'opacity-100' : 'opacity-0 pointer-events-none'}`}>
          <LoadingScreen
              text={isAuthenticated ? "正在加载工作台..." : (isShareRoute ? "正在解析分享内容..." : "正在启动智能引擎...")}
              isVisible={shouldShowLoading}
          />
        </div>

        <LoginModal
          isOpen={authModalView === 'login'}
          onClose={() => setAuthModalView('closed')}
          onSwitchToRegister={() => setAuthModalView('register')}
          onLoginSuccess={handleLoginSuccess}
        />
        <RegisterModal
          isOpen={authModalView === 'register'}
          onClose={() => setAuthModalView('closed')}
          onSwitchToLogin={() => setAuthModalView('login')}
          onRegisterSuccess={handleRegisterSuccess}
        />
      </ThemeProvider>
    </ErrorBoundary>
  );
}
