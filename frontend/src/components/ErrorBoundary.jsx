import React from 'react';
import StatePanel from './StatePanel';



class ErrorBoundary extends React.Component {

  constructor(props) {

    super(props);

    this.state = { hasError: false, error: null, errorInfo: null };

  }



  static getDerivedStateFromError() {

    return { hasError: true };

  }



  componentDidCatch(error, errorInfo) {

    this.setState({ error, errorInfo });

    console.error("React Error Boundary Caught:", error, errorInfo);

  }



  render() {

    if (this.state.hasError) {

      return (
        <StatePanel
          fullScreen
          tone="rose"
          icon="error"
          title="页面遇到了一点问题"
          description="渲染组件时发生了异常。你可以先刷新页面，若问题持续出现，再联系管理员排查。"
          actions={[
            { label: '返回首页', href: '/' },
            { label: '刷新页面', onClick: () => window.location.reload(), primary: true },
          ]}
        >
          <div className="rounded-2xl border border-rose-200 bg-white p-4 text-left dark:border-rose-900/60 dark:bg-slate-950">
            <p className="font-mono text-sm font-bold text-rose-600 dark:text-rose-300">
              {this.state.error && this.state.error.toString()}
            </p>
            <pre className="mt-3 max-h-[260px] overflow-auto whitespace-pre-wrap text-xs text-slate-500 dark:text-slate-400">
              {this.state.errorInfo && this.state.errorInfo.componentStack}
            </pre>
          </div>
        </StatePanel>

      );

    }



    return this.props.children;

  }

}



export default ErrorBoundary;
