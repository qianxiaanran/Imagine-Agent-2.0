import React from 'react';

import { AlertTriangle } from 'lucide-react';



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

        <div className="flex flex-col items-center justify-center h-screen bg-red-50 text-red-900 p-6 text-center">

          <AlertTriangle size={48} className="mb-4 text-red-500" />

          <h2 className="text-2xl font-bold mb-2">页面遇到了一点问题</h2>

          <p className="mb-6 text-red-700">加载组件时发生了错误。</p>



          <div className="bg-white p-4 rounded-lg shadow-sm border border-red-200 text-left w-full max-w-2xl overflow-auto max-h-[300px]">

            <p className="font-mono text-sm font-bold text-red-600 mb-2">

              {this.state.error && this.state.error.toString()}

            </p>

            <pre className="font-mono text-xs text-gray-500 whitespace-pre-wrap">

              {this.state.errorInfo && this.state.errorInfo.componentStack}

            </pre>

          </div>



          <button

            onClick={() => window.location.reload()}

            className="mt-8 px-6 py-2 bg-red-600 text-white rounded-lg hover:bg-red-700 transition-colors"

          >

            刷新页面

          </button>

        </div>

      );

    }



    return this.props.children;

  }

}



export default ErrorBoundary;
