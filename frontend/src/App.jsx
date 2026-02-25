import React, { Suspense, useEffect, useState } from 'react';
import ThemeProvider from './context/ThemeContext';
import GlobalStyles from './components/GlobalStyles';
import LoadingScreen from './components/LoadingScreen';
import ErrorBoundary from './components/ErrorBoundary';
import { AUTH_TOKEN_KEY } from './api/apiClient';

const loadLandingPage = () => import('./pages/LandingPage');
const loadCapabilitiesPage = () => import('./pages/CapabilitiesPage');
const loadQuickStartPage = () => import('./pages/QuickStartPage');
const loadDashboardPage = () => import('./pages/Dashboard/DashboardPage');
const loadSharedPage = () => import('./pages/Dashboard/SharedChatPage');
const loadAdminPage = () => import('./pages/Admin/AdminPage');
const loadLoginModal = () => import('./pages/Login/LoginModal');
const loadRegisterModal = () => import('./pages/Login/RegisterModal');

const LandingPage = React.lazy(loadLandingPage);
const CapabilitiesPage = React.lazy(loadCapabilitiesPage);
const QuickStartPage = React.lazy(loadQuickStartPage);
const DashboardPage = React.lazy(loadDashboardPage);
const SharedChatPage = React.lazy(loadSharedPage);
const AdminPage = React.lazy(loadAdminPage);
const LoginModal = React.lazy(loadLoginModal);
const RegisterModal = React.lazy(loadRegisterModal);

let supabaseClientPromise;
const getSupabaseClient = async () => {
  if (!supabaseClientPromise) {
    supabaseClientPromise = import('./api/supabaseClient').then((module) => module.supabase);
  }
  return supabaseClientPromise;
};

let userApiPromise;
const getUserApi = async () => {
  if (!userApiPromise) {
    userApiPromise = import('./api/user').then((module) => module.default);
  }
  return userApiPromise;
};

export default function App() {
  const [authModalView, setAuthModalView] = useState('closed');
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [currentMode, setCurrentMode] = useState('general');
  const [isAuthReady, setIsAuthReady] = useState(false);

  const REMEMBER_UNTIL_KEY = 'app_auth_remember_until';

  const normalizedPath = (window.location.pathname || '/').replace(/\/+$/, '') || '/';
  const isShareRoute = normalizedPath.startsWith('/share/');
  const isAdminRoute = normalizedPath.startsWith('/admin');
  const isCapabilitiesRoute = normalizedPath === '/capabilities';
  const isQuickStartRoute = normalizedPath === '/quickstart';
  const shouldShowLoading = !isAuthReady;

  useEffect(() => {
    let unsubscribe = null;
    let isDisposed = false;

    (async () => {
      const supabase = await getSupabaseClient();
      if (isDisposed) return;

      const { data } = supabase.auth.onAuthStateChange((_event, session) => {
        const rememberUntil = Number(localStorage.getItem(REMEMBER_UNTIL_KEY) || 0);
        if (!rememberUntil) return;

        if (rememberUntil <= Date.now()) {
          void supabase.auth.signOut();
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

      unsubscribe = () => data?.subscription?.unsubscribe();
    })();

    return () => {
      isDisposed = true;
      unsubscribe?.();
    };
  }, []);

  useEffect(() => {
    if (isShareRoute) {
      setIsAuthReady(true);
      loadSharedPage();
      return;
    }

    const preloadPublicPage = () => {
      if (isCapabilitiesRoute) {
        loadCapabilitiesPage();
        return;
      }
      if (isQuickStartRoute) {
        loadQuickStartPage();
        return;
      }
      loadLandingPage();
    };

    const checkAuth = async () => {
      let isValidSession = false;
      const settleAuth = () => setIsAuthReady(true);

      try {
        const rememberUntil = Number(localStorage.getItem(REMEMBER_UNTIL_KEY) || 0);
        const hasStoredToken = !!localStorage.getItem(AUTH_TOKEN_KEY);
        const hasAuthHint = rememberUntil > 0 || hasStoredToken;

        if (!hasAuthHint) {
          preloadPublicPage();
          settleAuth();
          return;
        }

        if (rememberUntil) {
          const supabase = await getSupabaseClient();
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
            const userApi = await getUserApi();
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
            console.warn('Token validation failed:', err);
            localStorage.removeItem(AUTH_TOKEN_KEY);
          }
        }
      } catch (error) {
        console.error('Auth check logic error', error);
      } finally {
        if (!isValidSession) preloadPublicPage();
        settleAuth();
      }
    };

    void checkAuth();
  }, [isShareRoute, isAdminRoute, isCapabilitiesRoute, isQuickStartRoute]);

  useEffect(() => {
    if (shouldShowLoading) {
      document.body.style.overflow = 'hidden';
      return () => {
        document.body.style.overflow = 'unset';
      };
    }

    const timer = setTimeout(() => {
      document.body.style.overflow = 'unset';
    }, 100);

    return () => clearTimeout(timer);
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

  const openLoginModal = () => {
    loadLoginModal();
    setAuthModalView('login');
  };

  const openRegisterModal = () => {
    loadRegisterModal();
    setAuthModalView('register');
  };

  const handleLoginSuccess = () => {
    setAuthModalView('closed');
    setIsAuthenticated(true);
    loadDashboardPage();
  };

  const handleRegisterSuccess = () => {
    setAuthModalView('closed');
    setIsAuthenticated(true);
    loadDashboardPage();
  };

  const handleLogout = () => {
    localStorage.removeItem(AUTH_TOKEN_KEY);
    localStorage.removeItem(REMEMBER_UNTIL_KEY);
    void getSupabaseClient().then((supabase) => supabase.auth.signOut());
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
            fallback={
              shouldShowLoading ? (
                <div className="min-h-screen bg-white dark:bg-gray-950"></div>
              ) : (
                <LoadingScreen text="正在加载页面..." isVisible />
              )
            }
          >
            {isShareRoute ? (
              <SharedChatPage />
            ) : isAuthenticated ? (
              isAdminRoute ? (
                <AdminPage />
              ) : (
                <DashboardPage onLogout={handleLogout} currentMode={currentMode} onModeChange={setCurrentMode} />
              )
            ) : isCapabilitiesRoute ? (
              <CapabilitiesPage onOpenLogin={openLoginModal} />
            ) : isQuickStartRoute ? (
              <QuickStartPage onOpenLogin={openLoginModal} />
            ) : (
              <LandingPage onOpenLogin={openLoginModal} />
            )}
          </Suspense>
        </div>

        <div className={`fixed inset-0 z-[9999] transition-opacity duration-500 ${shouldShowLoading ? 'opacity-100' : 'opacity-0 pointer-events-none'}`}>
          <LoadingScreen
            text={
              isAuthenticated
                ? '正在加载工作台...'
                : isShareRoute
                  ? '正在解析分享内容...'
                  : '正在启动智能引擎...'
            }
            isVisible={shouldShowLoading}
          />
        </div>

        <Suspense fallback={null}>
          {authModalView === 'login' && (
            <LoginModal
              isOpen
              onClose={() => setAuthModalView('closed')}
              onSwitchToRegister={openRegisterModal}
              onLoginSuccess={handleLoginSuccess}
            />
          )}

          {authModalView === 'register' && (
            <RegisterModal
              isOpen
              onClose={() => setAuthModalView('closed')}
              onSwitchToLogin={openLoginModal}
              onRegisterSuccess={handleRegisterSuccess}
            />
          )}
        </Suspense>
      </ThemeProvider>
    </ErrorBoundary>
  );
}
