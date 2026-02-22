import React, { useState, useEffect } from 'react';
import {
  Bot, Menu, X, Sun, Moon, ChevronRight, ArrowRight,
  Database, FileText, LayoutTemplate, Search, Cpu, Globe, Lock, ShieldCheck, Mic, Sparkles, ClipboardCheck, Share2, Rocket
} from 'lucide-react';
import Button from '../components/Button';
import { useTheme } from '../context/ThemeContext';
import useReveal from '../hooks/useReveal';

// 内部小组件：SectionBadge
const SectionBadge = ({ children }) => (
  <div className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-gray-50 border border-gray-200 text-xs font-bold text-gray-600 uppercase tracking-wider mb-6 hover:bg-gray-100 transition-colors cursor-default dark:bg-gray-800 dark:border-gray-700 dark:text-gray-300 dark:hover:bg-gray-700">
    <Sparkles size={12} className="text-blue-500" />
    {children}
  </div>
);

// 内部小组件：Reveal
const Reveal = ({ children, className = "", delay = 0 }) => {
  const { ref, className: revealClass, style } = useReveal(delay);
  return (
    <div ref={ref} className={`${revealClass} ${className}`} style={style}>
      {children}
    </div>
  );
};

const LandingPage = ({ onOpenLogin }) => {
  const [isScrolled, setIsScrolled] = useState(false);
  const [isMobileMenuOpen, setIsMobileMenuOpen] = useState(false);
  const [isAboutModalOpen, setIsAboutModalOpen] = useState(false);
  const [isContactModalOpen, setIsContactModalOpen] = useState(false);
  const [activeLegalModal, setActiveLegalModal] = useState('');

  // 使用 context 中的 theme
  const { toggleTheme, currentTheme } = useTheme();

  useEffect(() => {
    const handleScroll = () => setIsScrolled(window.scrollY > 20);
    window.addEventListener('scroll', handleScroll);
    return () => window.removeEventListener('scroll', handleScroll);
  }, []);

  useEffect(() => {
    if (!isAboutModalOpen && !isContactModalOpen && !activeLegalModal) return;

    const handleKeyDown = (event) => {
      if (event.key === 'Escape') {
        setIsAboutModalOpen(false);
        setIsContactModalOpen(false);
        setActiveLegalModal('');
      }
    };

    const originalOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    window.addEventListener('keydown', handleKeyDown);

    return () => {
      document.body.style.overflow = originalOverflow;
      window.removeEventListener('keydown', handleKeyDown);
    };
  }, [isAboutModalOpen, isContactModalOpen, activeLegalModal]);

  const navLinks = [
    { name: '功能特性', href: '#features' },
    { name: '解决方案', href: '#solutions' },
    { name: '能力详情', href: '/capabilities' },
    { name: '快速上手', href: '/quickstart' },
  ];

  return (
    <div
      className="min-h-screen bg-white dark:bg-gray-950 font-sans text-gray-900 dark:text-gray-100 selection:bg-gray-900 selection:text-white dark:selection:bg-white dark:selection:text-black overflow-x-hidden animate-in fade-in duration-500 transition-colors"
      style={{ minHeight: 'var(--app-height, 100vh)' }}
    >
      {/* Navigation */}
      <nav className={`fixed top-0 left-0 right-0 z-50 transition-all duration-300 ${isScrolled ? 'bg-white/90 dark:bg-gray-950/90 backdrop-blur-xl border-b border-gray-100 dark:border-gray-800 py-3 shadow-sm' : 'bg-transparent py-5'}`}>
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 flex justify-between items-center">
          <a href="#" className="flex items-center gap-2.5 group">
            <div className="w-9 h-9 bg-gray-900 dark:bg-white rounded-xl flex items-center justify-center text-white dark:text-black shadow-lg shadow-gray-900/20 group-hover:scale-105 transition-transform duration-300"><Bot size={20} /></div>
            <span className="text-lg font-bold tracking-tight text-gray-900 dark:text-white">企业智能办公</span>
          </a>

          {/* Desktop Menu */}
          <div className="hidden md:flex items-center gap-8 bg-gray-50/80 dark:bg-gray-800/80 px-6 py-2 rounded-full border border-gray-100/50 dark:border-gray-700/50 backdrop-blur-sm">
            {navLinks.map((link) => (
              <a key={link.name} href={link.href} className="text-sm font-medium text-gray-500 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white transition-colors relative group">{link.name}<span className="absolute -bottom-1 left-0 w-0 h-0.5 bg-gray-900 dark:bg-white transition-all duration-300 group-hover:w-full"></span></a>
            ))}
          </div>

          <div className="hidden md:flex items-center gap-4">
            <button
                onClick={toggleTheme}
                className="p-2 rounded-full text-gray-600 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors"
                title="切换外观"
            >
                {currentTheme === 'dark' ? <Moon size={20} /> : <Sun size={20} />}
            </button>
            <Button variant="ghost" className="!px-4 text-sm font-medium" onClick={onOpenLogin}>登录</Button>
            <Button variant="primary" className="!px-5 !py-2 !text-sm !shadow-md" onClick={onOpenLogin}>开始使用</Button>
          </div>

          {/* Mobile Menu Toggle */}
          <button className="md:hidden p-2 text-gray-600 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-800 rounded-lg transition-colors" onClick={() => setIsMobileMenuOpen(!isMobileMenuOpen)}>{isMobileMenuOpen ? <X size={24} /> : <Menu size={24} />}</button>
        </div>

        {/* Mobile Menu Dropdown */}
        {isMobileMenuOpen && (
          <div className="absolute top-full left-0 right-0 bg-white dark:bg-gray-900 border-b border-gray-100 dark:border-gray-800 p-4 md:hidden flex flex-col gap-4 shadow-xl animate-in slide-in-from-top-5">
            {navLinks.map((link) => (
              <a key={link.name} href={link.href} className="text-base font-medium text-gray-900 dark:text-white py-3 px-4 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-800" onClick={() => setIsMobileMenuOpen(false)}>{link.name}</a>
            ))}
            <div className="h-px bg-gray-100 dark:bg-gray-800 my-2"></div>
            <div className="flex items-center justify-between px-4">
                <span className="text-sm font-medium text-gray-900 dark:text-white">外观模式</span>
                <button onClick={toggleTheme} className="p-2 rounded-full text-gray-600 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors">
                    {currentTheme === 'dark' ? <Moon size={20} /> : <Sun size={20} />}
                </button>
            </div>
            <Button variant="ghost" className="w-full" onClick={() => { setIsMobileMenuOpen(false); onOpenLogin(); }}>登录</Button>
            <Button variant="primary" className="w-full mt-2" onClick={() => { setIsMobileMenuOpen(false); onOpenLogin(); }}>立即开始</Button>
          </div>
        )}
      </nav>

      {/* Hero Section */}
      <section className="relative pt-32 pb-20 lg:pt-48 lg:pb-32 overflow-hidden">
        {/* Background Effects */}
        <div className="absolute top-0 inset-x-0 h-[800px] bg-[radial-gradient(ellipse_80%_50%_at_50%_-20%,rgba(120,119,198,0.15),rgba(255,255,255,0))] dark:bg-[radial-gradient(ellipse_80%_50%_at_50%_-20%,rgba(120,119,198,0.3),rgba(0,0,0,0))]" />
        <div className="absolute top-40 right-0 w-[500px] h-[500px] bg-blue-50/50 dark:bg-blue-900/20 rounded-full blur-3xl -z-10 opacity-60 animate-pulse-soft"></div>
        <div className="absolute top-60 left-0 w-[400px] h-[400px] bg-purple-50/50 dark:bg-purple-900/20 rounded-full blur-3xl -z-10 opacity-60 animate-pulse-soft" style={{animationDelay: '1s'}}></div>

        <div className="max-w-5xl mx-auto px-4 text-center relative z-10">
          <Reveal>
            <div className="inline-flex items-center gap-2 px-4 py-1.5 rounded-full bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 text-xs font-semibold text-gray-600 dark:text-gray-300 mb-8 shadow-sm hover:border-gray-300 dark:hover:border-gray-600 transition-colors cursor-pointer">
              <span className="relative flex h-2 w-2">
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-green-400 opacity-75"></span>
                <span className="relative inline-flex rounded-full h-2 w-2 bg-green-500"></span>
              </span>
              v2.0 已上线：支持语音、OCR、审单、知识库与数据库协同 <ChevronRight size={14} className="text-gray-400" />
            </div>
          </Reveal>
          <Reveal delay={100}>
            <h1 className="text-5xl md:text-7xl font-bold tracking-tight text-gray-900 dark:text-white mb-8 leading-[1.15]">
              让企业知识库 <br className="hidden md:block" />
              <span className="relative whitespace-nowrap">
                <span className="relative z-10 bg-clip-text text-transparent bg-gradient-to-r from-gray-900 via-gray-600 to-gray-900 dark:from-white dark:via-gray-300 dark:to-white">主动思考与协作</span>
                <span className="absolute bottom-2 left-0 w-full h-3 bg-blue-100/50 dark:bg-blue-900/30 -z-10 -rotate-1 rounded-full"></span>
              </span>
            </h1>
          </Reveal>
          <Reveal delay={200}>
            <p className="text-lg md:text-xl text-gray-500 dark:text-gray-400 mb-10 max-w-2xl mx-auto leading-relaxed">不只做问答，还把文档、数据库、语音、OCR、审单、写作串成一条业务链。<br className="hidden md:block" />一个入口就能覆盖多数企业日常协作场景。</p>
          </Reveal>
          <Reveal delay={300}>
            <div className="flex flex-col sm:flex-row items-center justify-center gap-4 mb-20">
              <Button variant="primary" className="w-full sm:w-auto text-lg px-8 py-4 shadow-xl shadow-gray-900/10 dark:shadow-white/5" icon={ArrowRight} onClick={onOpenLogin}>登录并开始使用</Button>
              <Button variant="outline" className="w-full sm:w-auto text-lg px-8 py-4 backdrop-blur-sm" onClick={() => { window.location.href = '/quickstart'; }}>查看快速上手</Button>
            </div>
          </Reveal>

          {/* Interactive SQL Demo Card */}
          <Reveal delay={400} className="relative mx-auto max-w-5xl px-4 md:px-0">
            <div className="animate-float relative rounded-2xl bg-gray-900/5 dark:bg-white/5 p-3 shadow-2xl ring-1 ring-gray-900/10 dark:ring-white/10 backdrop-blur-sm">
              <div className="absolute -top-4 -right-4 w-24 h-24 bg-gradient-to-br from-blue-400 to-purple-500 rounded-full blur-2xl opacity-20"></div>
              <div className="aspect-[16/9] rounded-xl bg-white dark:bg-gray-900 overflow-hidden flex flex-col shadow-inner border border-white/50 dark:border-gray-800">
                <div className="h-12 border-b border-gray-100 dark:border-gray-800 flex items-center px-4 justify-between bg-gray-50/80 dark:bg-gray-800/80 backdrop-blur-md sticky top-0 z-10">
                  <div className="flex gap-2"><div className="w-3 h-3 rounded-full bg-red-400/80 border border-red-500/20"></div><div className="w-3 h-3 rounded-full bg-yellow-400/80 border border-yellow-500/20"></div><div className="w-3 h-3 rounded-full bg-green-400/80 border border-green-500/20"></div></div>
                  <div className="flex gap-6 text-xs text-gray-400 font-medium"><span>知识库</span><span>数据查询</span><span>会议纪要</span></div>
                  <div className="w-4"></div>
                </div>
                <div className="flex-1 flex bg-white/50 dark:bg-gray-900/50">
                  <div className="w-56 border-r border-gray-100 dark:border-gray-800 bg-gray-50/50 dark:bg-gray-800/50 p-5 hidden md:block">
                     <div className="flex items-center gap-2 mb-6 text-gray-900 dark:text-white font-bold text-sm"><Database size={16} /> 数据源管理</div>
                     <div className="space-y-3">
                       <div className="flex items-center justify-between text-xs text-gray-600 dark:text-gray-300 bg-white dark:bg-gray-900 p-2 rounded border border-gray-100 dark:border-gray-700 shadow-sm"><span className="flex items-center gap-2"><div className="w-1.5 h-1.5 rounded-full bg-green-500"></div>销售数据库.db</span></div>
                       <div className="flex items-center justify-between text-xs text-gray-400 hover:bg-white/50 dark:hover:bg-gray-800/50 p-2 rounded transition-colors cursor-pointer"><span className="flex items-center gap-2"><div className="w-1.5 h-1.5 rounded-full bg-gray-300 dark:bg-gray-600"></div>人力资源.db</span></div>
                       <div className="h-px bg-gray-100 dark:bg-gray-800 my-4"></div>
                       <div className="h-2 w-24 bg-gray-200/50 dark:bg-gray-700/50 rounded animate-pulse"></div>
                       <div className="h-2 w-16 bg-gray-200/50 dark:bg-gray-700/50 rounded animate-pulse"></div>
                     </div>
                  </div>
                  <div className="flex-1 p-6 md:p-10 flex flex-col justify-end relative overflow-hidden">
                    <div className="absolute inset-0 bg-[radial-gradient(#e5e7eb_1px,transparent_1px)] dark:bg-[radial-gradient(#333_1px,transparent_1px)] [background-size:16px_16px] [mask-image:radial-gradient(ellipse_50%_50%_at_50%_50%,#000_70%,transparent_100%)] opacity-20 pointer-events-none"></div>
                    <div className="space-y-8 z-0">
                      <div className="flex gap-4">
                        <div className="w-9 h-9 rounded-full bg-gray-100 dark:bg-gray-800 flex items-center justify-center flex-shrink-0 text-gray-500 dark:text-gray-400 border border-gray-200 dark:border-gray-700"><span className="text-xs font-bold">U</span></div>
                        <div className="bg-white dark:bg-gray-800 p-5 rounded-2xl rounded-tl-none shadow-sm border border-gray-100 dark:border-gray-700 text-sm text-gray-600 dark:text-gray-300 max-w-lg leading-relaxed">请分析 Q3 季度的销售数据，找出增长最快的产品线，并生成 SQL 查询语句。</div>
                      </div>
                      <div className="flex gap-4 flex-row-reverse">
                        <div className="w-9 h-9 rounded-full bg-gradient-to-br from-gray-800 to-black dark:from-white dark:to-gray-200 flex items-center justify-center flex-shrink-0 text-white dark:text-black shadow-lg"><Bot size={16} /></div>
                        <div className="bg-blue-50/80 dark:bg-blue-900/30 backdrop-blur-sm p-5 rounded-2xl rounded-tr-none shadow-sm border border-blue-100 dark:border-blue-800 text-sm text-gray-800 dark:text-gray-200 max-w-xl group hover:shadow-md transition-shadow">
                          <div className="flex items-center gap-2 mb-3 text-blue-800 dark:text-blue-300 font-semibold text-xs uppercase tracking-wider"><Sparkles size={12} /> AI 分析结果</div>
                          <p className="mb-3">根据数据库结构，已为您生成查询。增长最快的是 <strong className="text-blue-700 dark:text-blue-400">“企业版许可”</strong> 产品线，环比增长 45%。</p>
                          <div className="bg-gray-900 dark:bg-black rounded-lg border border-gray-800 dark:border-gray-700 p-3 mb-3 text-xs font-mono text-gray-300 overflow-x-auto"><span className="text-purple-400">SELECT</span> product_line, <span className="text-purple-400">SUM</span>(revenue) <span className="text-purple-400">AS</span> total <br/><span className="text-purple-400">FROM</span> sales_q3 <br/><span className="text-purple-400">GROUP BY</span> product_line <br/><span className="text-purple-400">ORDER BY</span> total <span className="text-purple-400">DESC</span> <span className="text-purple-400">LIMIT</span> 1;</div>
                          <div className="flex gap-2"><button className="text-xs bg-white dark:bg-gray-800 border border-blue-200 dark:border-blue-700 text-blue-600 dark:text-blue-300 px-3 py-1.5 rounded-full hover:bg-blue-50 dark:hover:bg-blue-900/30 transition-colors">执行查询</button><button className="text-xs bg-transparent text-gray-400 px-3 py-1.5 hover:text-gray-600 dark:hover:text-gray-200">复制 SQL</button></div>
                        </div>
                      </div>
                    </div>
                    <div className="mt-10 relative z-10">
                      <div className="h-14 bg-white/80 dark:bg-gray-800/80 backdrop-blur border border-gray-200 dark:border-gray-700 rounded-2xl shadow-lg shadow-gray-100/50 dark:shadow-none flex items-center px-2 pl-5 justify-between focus-within:ring-2 focus-within:ring-gray-900/10 dark:focus-within:ring-white/10 transition-all">
                        <span className="text-gray-400 text-sm">输入问题或指令，支持语音...</span>
                        <div className="flex items-center gap-1"><button className="p-2 text-gray-400 hover:text-gray-600 dark:hover:text-gray-200 hover:bg-gray-100 dark:hover:bg-gray-700 rounded-lg transition-colors"><Mic size={18} /></button><button className="p-2 bg-black dark:bg-white text-white dark:text-black rounded-xl shadow-lg shadow-black/20 dark:shadow-white/20 hover:scale-105 transition-transform"><ArrowRight size={18} /></button></div>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
              <div className="absolute -left-6 bottom-20 bg-white/90 dark:bg-gray-800/90 backdrop-blur p-4 rounded-2xl shadow-xl border border-gray-100 dark:border-gray-700 animate-float hidden md:block" style={{animationDelay: '1.5s'}}>
                 <div className="flex items-center gap-3">
                   <div className="bg-green-100 dark:bg-green-900/30 p-2 rounded-lg text-green-600 dark:text-green-400"><Database size={20} /></div>
                   <div><div className="text-xs text-gray-500 dark:text-gray-400 font-medium">已连接数据库</div><div className="text-sm font-bold text-gray-900 dark:text-white">PostgreSQL / MySQL</div></div>
                 </div>
              </div>
            </div>
          </Reveal>
        </div>
      </section>

      {/* Features Section */}
      <section id="features" className="py-32 bg-gray-50/50 dark:bg-gray-900/50">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <Reveal>
            <div className="text-center mb-20">
              <SectionBadge>核心能力</SectionBadge>
              <h2 className="text-4xl md:text-5xl font-bold text-gray-900 dark:text-white mb-6 tracking-tight">打造企业专属的“第二大脑”</h2>
              <p className="text-gray-500 dark:text-gray-400 text-lg max-w-2xl mx-auto">传统的 OA 系统只记录流程，我们利用 AI 激活数据。<br />从文档到数据库，从会议到决策，全链路智能化赋能。</p>
            </div>
          </Reveal>
          <div className="grid grid-cols-1 md:grid-cols-6 md:grid-rows-2 gap-6 h-auto md:h-[800px]">
            {/* Card 1: Document Parsing */}
            <Reveal className="md:col-span-4 bg-white dark:bg-gray-800 rounded-[2rem] p-10 border border-gray-100 dark:border-gray-700 shadow-sm hover:shadow-2xl hover:border-blue-100 dark:hover:border-blue-900 hover:-translate-y-1 transition-all duration-300 relative overflow-hidden group">
              <div className="relative z-10 h-full flex flex-col justify-between">
                <div>
                  <div className="w-14 h-14 bg-blue-50 dark:bg-blue-900/20 rounded-2xl flex items-center justify-center mb-6 text-blue-600 dark:text-blue-400 group-hover:scale-110 transition-transform duration-500"><FileText size={28} /></div>
                  <h3 className="text-2xl font-bold text-gray-900 dark:text-white mb-3">多模态文档深度解析</h3>
                  <p className="text-gray-500 dark:text-gray-400 max-w-md leading-relaxed">不仅是关键词匹配。利用 RAG 技术与 Paddle OCR，精准提取扫描件、合同条款中的语义信息。支持来源溯源，点击引用直接跳转原文高亮位置。</p>
                </div>
                <div className="mt-8 flex gap-3">{['.PDF', '.DOCX', '.TXT', 'OCR'].map((tag, i) => (<span key={i} className="px-3 py-1 bg-gray-50 dark:bg-gray-700 border border-gray-100 dark:border-gray-600 rounded-lg text-xs font-bold text-gray-400 dark:text-gray-300 group-hover:text-blue-600 dark:group-hover:text-blue-400 group-hover:border-blue-100 dark:group-hover:border-blue-800 transition-colors">{tag}</span>))}</div>
              </div>
              <div className="absolute right-[-20px] bottom-[-20px] w-80 h-80 bg-gradient-to-tl from-blue-100/50 dark:from-blue-900/30 to-transparent rounded-full blur-3xl opacity-0 group-hover:opacity-100 transition-opacity duration-500"></div>
            </Reveal>

            {/* Card 2: Chat to SQL */}
            <Reveal className="md:col-span-2 md:row-span-2 bg-gray-900 dark:bg-black rounded-[2rem] p-10 text-white relative overflow-hidden group flex flex-col" delay={100}>
              <div className="absolute inset-0 bg-[linear-gradient(to_bottom,transparent_0%,rgba(255,255,255,0.05)_100%)] opacity-0 group-hover:opacity-100 transition-opacity duration-500"></div>
              <div className="relative z-10 flex-1 flex flex-col">
                <div className="w-14 h-14 bg-white/10 backdrop-blur-md rounded-2xl flex items-center justify-center mb-6 border border-white/10 group-hover:bg-white/20 transition-colors"><Database size={28} className="text-white" /></div>
                <h3 className="text-2xl font-bold mb-4">Chat to SQL</h3>
                <p className="text-gray-400 leading-relaxed mb-8">让每一位员工都具备数据分析师的能力。<br/><br/>无需学习复杂的 SQL 语法，直接使用自然语言提问。系统自动识别表结构、字段关联，智能生成并执行查询。</p>
                <div className="mt-auto bg-black/50 rounded-xl p-4 border border-white/10 font-mono text-xs backdrop-blur-sm shadow-inner group-hover:border-white/20 transition-colors">
                  <div className="flex gap-1.5 mb-3"><div className="w-2.5 h-2.5 rounded-full bg-red-500"></div><div className="w-2.5 h-2.5 rounded-full bg-yellow-500"></div><div className="w-2.5 h-2.5 rounded-full bg-green-500"></div></div>
                  <div className="space-y-2 opacity-80"><p className="text-gray-500"># User Query:</p><p className="text-white">"Show top 3 customers"</p><p className="text-gray-500 mt-2"># Generated SQL:</p><p className="text-green-400">SELECT name, total <br/>FROM customers <br/>ORDER BY total DESC <br/>LIMIT 3;</p></div>
                </div>
              </div>
            </Reveal>

            {/* Card 3: Voice */}
            <Reveal className="md:col-span-2 bg-white dark:bg-gray-800 rounded-[2rem] p-10 border border-gray-100 dark:border-gray-700 shadow-sm hover:shadow-2xl hover:border-red-100 dark:hover:border-red-900 hover:-translate-y-1 transition-all duration-300 group" delay={200}>
              <div className="w-12 h-12 bg-red-50 dark:bg-red-900/20 rounded-2xl flex items-center justify-center mb-6 text-red-500 group-hover:rotate-12 transition-transform"><Mic size={24} /></div>
              <h3 className="text-xl font-bold text-gray-900 dark:text-white mb-2">会议语音转写</h3>
              <p className="text-gray-500 dark:text-gray-400 text-sm leading-relaxed">支持录音上传与即时语音输入，自动转写并生成会议纪要，结果可继续追问和编辑。</p>
            </Reveal>

            {/* Card 4: Privacy */}
            <Reveal className="md:col-span-2 bg-white dark:bg-gray-800 rounded-[2rem] p-10 border border-gray-100 dark:border-gray-700 shadow-sm hover:shadow-2xl hover:border-green-100 dark:hover:border-green-900 hover:-translate-y-1 transition-all duration-300 group" delay={300}>
              <div className="w-12 h-12 bg-green-50 dark:bg-green-900/20 rounded-2xl flex items-center justify-center mb-6 text-green-600 group-hover:scale-110 transition-transform"><ShieldCheck size={24} /></div>
              <h3 className="text-xl font-bold text-gray-900 dark:text-white mb-2">私有化部署</h3>
              <p className="text-gray-500 dark:text-gray-400 text-sm leading-relaxed">数据不出域。基于 Qwen2.5-coder 本地模型与 Chroma 向量库，构建完全可控的企业数据壁垒。</p>
            </Reveal>
          </div>
        </div>
      </section>

      {/* Technical Architecture Section */}
      <section id="tech" className="py-32 bg-white dark:bg-gray-950 relative overflow-hidden">
        <div className="absolute inset-0 bg-[linear-gradient(to_right,#80808012_1px,transparent_1px),linear-gradient(to_bottom,#80808012_1px,transparent_1px)] bg-[size:24px_24px]"></div>
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 relative z-10">
          <div className="grid md:grid-cols-2 gap-20 items-center">
            <Reveal className="order-2 md:order-1">
              <SectionBadge>技术架构</SectionBadge>
              <h2 className="text-4xl font-bold text-gray-900 dark:text-white mb-6 leading-tight">模块化设计，<br />为企业级性能而生</h2>
              <p className="text-gray-500 dark:text-gray-400 text-lg mb-10 leading-relaxed">摒弃了黑盒交付。系统采用清晰的分层架构，业务逻辑与 AI 服务解耦，既保证了系统的稳定性，也为未来的模型升级预留了无限可能。</p>
              <div className="space-y-8">
                {[{ title: '多模态智能输入', desc: '统一处理 PDF/Word 文档、数据库表结构与语音流，消除数据孤岛。', icon: LayoutTemplate, color: 'text-blue-600 dark:text-blue-400', bg: 'bg-blue-50 dark:bg-blue-900/20' }, { title: '混合检索引擎', desc: '结合 BGE 中文嵌入模型与关键词搜索，在召回率与准确率之间找到完美平衡。', icon: Search, color: 'text-purple-600 dark:text-purple-400', bg: 'bg-purple-50 dark:bg-purple-900/20' }, { title: '本地模型生态', desc: '深度适配 Qwen2.5-coder、DeepSeek 等开源大模型，低成本实现高性能推理。', icon: Cpu, color: 'text-gray-900 dark:text-white', bg: 'bg-gray-100 dark:bg-gray-800' }].map((item, idx) => (
                  <div key={idx} className="flex gap-5 group">
                    <div className="mt-1 flex-shrink-0"><div className={`w-12 h-12 rounded-2xl ${item.bg} flex items-center justify-center ${item.color} group-hover:scale-110 transition-transform duration-300`}><item.icon size={20} strokeWidth={2} /></div></div>
                    <div><h4 className="font-bold text-gray-900 dark:text-white text-lg group-hover:text-blue-600 dark:group-hover:text-blue-400 transition-colors">{item.title}</h4><p className="text-gray-500 dark:text-gray-400 mt-2 leading-relaxed">{item.desc}</p></div>
                  </div>
                ))}
              </div>
            </Reveal>
            <Reveal className="order-1 md:order-2" delay={200}>
              <div className="relative">
                <div className="absolute inset-0 bg-gradient-to-tr from-gray-100 to-gray-50 dark:from-gray-800 dark:to-gray-900 rounded-[2.5rem] transform rotate-3 scale-95 opacity-50"></div>
                <div className="bg-white dark:bg-gray-900 rounded-[2.5rem] p-8 border border-gray-100 dark:border-gray-800 shadow-2xl relative z-10">
                   <div className="space-y-6">
                      <div className="bg-white dark:bg-gray-800 p-6 rounded-2xl shadow-sm border border-gray-100 dark:border-gray-700 flex items-center justify-between group hover:border-blue-200 dark:hover:border-blue-800 transition-colors cursor-default">
                        <div className="flex items-center gap-3"><div className="w-2 h-2 rounded-full bg-green-500 animate-pulse"></div><span className="font-bold text-gray-800 dark:text-gray-200">React 前端交互层</span></div>
                        <Globe size={18} className="text-gray-400 group-hover:text-blue-500 transition-colors" />
                      </div>
                      <div className="flex justify-center h-8 relative"><div className="w-px bg-gray-200 dark:bg-gray-700 h-full absolute left-1/2 -translate-x-1/2"></div></div>
                      <div className="grid grid-cols-3 gap-4">
                        <div className="bg-blue-50/50 dark:bg-blue-900/20 p-4 rounded-2xl border border-blue-100 dark:border-blue-800 text-center hover:bg-blue-50 dark:hover:bg-blue-900/30 transition-colors"><FileText size={20} className="mx-auto text-blue-600 dark:text-blue-400 mb-2" /><div className="text-xs font-bold text-blue-900 dark:text-blue-300">文档处理</div></div>
                        <div className="bg-purple-50/50 dark:bg-purple-900/20 p-4 rounded-2xl border border-purple-100 dark:border-purple-800 text-center hover:bg-purple-50 dark:hover:bg-purple-900/30 transition-colors"><Database size={20} className="mx-auto text-purple-600 dark:text-purple-400 mb-2" /><div className="text-xs font-bold text-purple-900 dark:text-purple-300">SQL 转换</div></div>
                        <div className="bg-red-50/50 dark:bg-red-900/20 p-4 rounded-2xl border border-red-100 dark:border-red-800 text-center hover:bg-red-50 dark:hover:bg-red-900/30 transition-colors"><Mic size={20} className="mx-auto text-red-600 dark:text-red-400 mb-2" /><div className="text-xs font-bold text-red-900 dark:text-red-300">语音分析</div></div>
                      </div>
                      <div className="flex justify-center h-8 relative"><div className="w-px bg-gray-200 dark:bg-gray-700 h-full absolute left-1/2 -translate-x-1/2"></div></div>
                      <div className="bg-gray-900 dark:bg-black p-8 rounded-2xl shadow-lg text-white relative overflow-hidden">
                        <div className="absolute top-0 right-0 w-32 h-32 bg-blue-500 rounded-full blur-3xl opacity-20"></div>
                        <div className="relative z-10">
                          <div className="flex items-center justify-between mb-6"><span className="font-bold text-lg">AI 核心服务层</span><span className="text-xs bg-gray-800 dark:bg-gray-900 px-2 py-1 rounded text-gray-400">Powered by LangChain</span></div>
                          <div className="grid grid-cols-2 gap-3 text-xs font-medium">
                            <div className="bg-gray-800 dark:bg-gray-900 p-3 rounded-lg border border-gray-700 flex items-center gap-2"><div className="w-1.5 h-1.5 bg-blue-400 rounded-full"></div> Chroma 向量库</div>
                            <div className="bg-gray-800 dark:bg-gray-900 p-3 rounded-lg border border-gray-700 flex items-center gap-2"><div className="w-1.5 h-1.5 bg-purple-400 rounded-full"></div> Qwen2.5-coder LLM</div>
                            <div className="bg-gray-800 dark:bg-gray-900 p-3 rounded-lg border border-gray-700 flex items-center gap-2"><div className="w-1.5 h-1.5 bg-green-400 rounded-full"></div> BGE Embedding</div>
                            <div className="bg-gray-800 dark:bg-gray-900 p-3 rounded-lg border border-gray-700 flex items-center gap-2"><div className="w-1.5 h-1.5 bg-yellow-400 rounded-full"></div> Baidu ASR + Queue</div>
                          </div>
                        </div>
                      </div>
                   </div>
                </div>
              </div>
            </Reveal>
          </div>
        </div>
      </section>

      {/* Solutions Section */}
      <section id="solutions" className="py-32 bg-gray-50/50 dark:bg-gray-900/40">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <Reveal>
            <div className="text-center mb-16">
              <SectionBadge>解决方案</SectionBadge>
              <h2 className="text-4xl md:text-5xl font-bold text-gray-900 dark:text-white mb-5 tracking-tight">按业务场景直接落地</h2>
              <p className="text-gray-500 dark:text-gray-400 text-lg max-w-2xl mx-auto">从“提问”到“交付”是一条完整链路，你可以按场景逐步启用，不需要一次性重构流程。</p>
            </div>
          </Reveal>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            <Reveal className="bg-white dark:bg-gray-800 rounded-[2rem] p-8 border border-gray-100 dark:border-gray-700 shadow-sm hover:shadow-xl transition-all duration-300">
              <div className="w-12 h-12 rounded-2xl bg-blue-50 dark:bg-blue-900/25 text-blue-600 dark:text-blue-300 flex items-center justify-center mb-5">
                <Rocket size={22} />
              </div>
              <h3 className="text-2xl font-bold text-gray-900 dark:text-white mb-3">运营分析提效</h3>
              <p className="text-sm text-gray-500 dark:text-gray-400 leading-relaxed mb-4">把数据库问答、联网搜索和报告写作串起来，快速完成“数据查询-结论归纳-输出汇报”。</p>
              <div className="text-xs text-gray-600 dark:text-gray-300">典型入口：数据库模式 + 报告/PPT 写作</div>
            </Reveal>

            <Reveal className="bg-white dark:bg-gray-800 rounded-[2rem] p-8 border border-gray-100 dark:border-gray-700 shadow-sm hover:shadow-xl transition-all duration-300" delay={120}>
              <div className="w-12 h-12 rounded-2xl bg-amber-50 dark:bg-amber-900/25 text-amber-600 dark:text-amber-300 flex items-center justify-center mb-5">
                <ClipboardCheck size={22} />
              </div>
              <h3 className="text-2xl font-bold text-gray-900 dark:text-white mb-3">单据风险把控</h3>
              <p className="text-sm text-gray-500 dark:text-gray-400 leading-relaxed mb-4">上传单据后触发审单任务，跟踪进度与风险分级，关键异常可同步到复核动作。</p>
              <div className="text-xs text-gray-600 dark:text-gray-300">典型入口：审单 Agent + OCR 识别</div>
            </Reveal>

            <Reveal className="bg-white dark:bg-gray-800 rounded-[2rem] p-8 border border-gray-100 dark:border-gray-700 shadow-sm hover:shadow-xl transition-all duration-300" delay={240}>
              <div className="w-12 h-12 rounded-2xl bg-emerald-50 dark:bg-emerald-900/25 text-emerald-600 dark:text-emerald-300 flex items-center justify-center mb-5">
                <Share2 size={22} />
              </div>
              <h3 className="text-2xl font-bold text-gray-900 dark:text-white mb-3">协作与知识沉淀</h3>
              <p className="text-sm text-gray-500 dark:text-gray-400 leading-relaxed mb-4">会话可保存上下文并生成分享链接，让纪要、文档解读和流程结论更容易流转给团队。</p>
              <div className="text-xs text-gray-600 dark:text-gray-300">典型入口：历史会话 + 分享链接</div>
            </Reveal>
          </div>
        </div>
      </section>

      {/* Footer */}
      <footer className="bg-white dark:bg-gray-950 border-t border-gray-100 dark:border-gray-800 pt-20 pb-10">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-12 mb-16">
            <div className="col-span-2 md:col-span-1">
              <div className="flex items-center gap-2.5 mb-6">
                 <div className="w-8 h-8 bg-gray-900 dark:bg-white rounded-lg flex items-center justify-center text-white dark:text-black"><Bot size={18} /></div>
                 <span className="font-bold text-xl text-gray-900 dark:text-white">智能办公</span>
              </div>
              <p className="text-sm text-gray-500 dark:text-gray-400 mb-6 leading-relaxed max-w-xs">基于 LLM 的企业级智能办公系统，致力于让信息处理更简单、更安全。</p>
              <div className="flex gap-4">
                 <div className="w-8 h-8 rounded-full bg-gray-100 dark:bg-gray-800 flex items-center justify-center hover:bg-gray-200 dark:hover:bg-gray-700 cursor-pointer transition-colors"><Globe size={14} className="text-gray-600 dark:text-gray-400"/></div>
                 <div className="w-8 h-8 rounded-full bg-gray-100 dark:bg-gray-800 flex items-center justify-center hover:bg-gray-200 dark:hover:bg-gray-700 cursor-pointer transition-colors"><Lock size={14} className="text-gray-600 dark:text-gray-400"/></div>
              </div>
            </div>
            <div>
              <h4 className="font-bold text-gray-900 dark:text-white mb-6">产品</h4>
              <ul className="space-y-4 text-sm text-gray-500 dark:text-gray-400">
                <li><a href="#features" className="hover:text-black dark:hover:text-white transition-colors">功能特性</a></li>
                <li><a href="#solutions" className="hover:text-black dark:hover:text-white transition-colors">解决方案</a></li>
                <li><a href="/capabilities" className="hover:text-black dark:hover:text-white transition-colors">能力详情</a></li>
                <li><a href="/quickstart" className="hover:text-black dark:hover:text-white transition-colors">快速上手</a></li>
              </ul>
            </div>
            <div>
              <h4 className="font-bold text-gray-900 dark:text-white mb-6">资源</h4>
              <ul className="space-y-4 text-sm text-gray-500 dark:text-gray-400">
                <li><a href="/quickstart" className="hover:text-black dark:hover:text-white transition-colors">使用手册</a></li>
                <li><a href="/capabilities" className="hover:text-black dark:hover:text-white transition-colors">集成清单</a></li>
                <li><button type="button" onClick={onOpenLogin} className="hover:text-black dark:hover:text-white transition-colors">登录体验</button></li>
                <li><a href="#tech" className="hover:text-black dark:hover:text-white transition-colors">架构概览</a></li>
              </ul>
            </div>
            <div>
              <h4 className="font-bold text-gray-900 dark:text-white mb-6">关于</h4>
              <ul className="space-y-4 text-sm text-gray-500 dark:text-gray-400">
                <li>
                  <button
                    type="button"
                    onClick={() => setIsAboutModalOpen(true)}
                    className="hover:text-black dark:hover:text-white transition-colors text-left"
                  >
                    关于我
                  </button>
                </li>
                <li>
                  <button
                    type="button"
                    onClick={() => setIsContactModalOpen(true)}
                    className="hover:text-black dark:hover:text-white transition-colors text-left"
                  >
                    联系方式
                  </button>
                </li>
                <li>
                  <button
                    type="button"
                    onClick={() => setActiveLegalModal('隐私政策')}
                    className="hover:text-black dark:hover:text-white transition-colors text-left"
                  >
                    隐私政策
                  </button>
                </li>
                <li>
                  <button
                    type="button"
                    onClick={() => setActiveLegalModal('服务条款')}
                    className="hover:text-black dark:hover:text-white transition-colors text-left"
                  >
                    服务条款
                  </button>
                </li>
              </ul>
            </div>
          </div>
          <div className="pt-8 border-t border-gray-100 dark:border-gray-800 flex flex-col md:flex-row justify-between items-center gap-4">
            <p className="text-xs text-gray-400 dark:text-gray-500">© 2026 Enterprise Intelligent Office Agent. All rights reserved.</p>
            <div className="flex items-center gap-2 text-xs text-gray-400 dark:text-gray-500"><div className="w-2 h-2 rounded-full bg-green-500"></div> 系统运行正常</div>
          </div>
        </div>
      </footer>

      {isAboutModalOpen && (
        <div className="fixed inset-0 z-[120] flex items-center justify-center p-4">
          <div className="absolute inset-0 bg-black/45 backdrop-blur-[2px]" onClick={() => setIsAboutModalOpen(false)}></div>
          <div className="relative w-full max-w-2xl rounded-2xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 shadow-2xl p-6 md:p-7 animate-in fade-in zoom-in-95 duration-200">
            <div className="flex items-start justify-between gap-4 mb-4">
              <h3 className="text-xl md:text-2xl font-bold text-gray-900 dark:text-white">关于我</h3>
              <button
                type="button"
                onClick={() => setIsAboutModalOpen(false)}
                className="p-2 rounded-lg text-gray-500 hover:text-gray-900 dark:text-gray-400 dark:hover:text-white hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors"
                aria-label="关闭"
              >
                <X size={18} />
              </button>
            </div>
            <p className="text-sm md:text-base leading-relaxed text-gray-700 dark:text-gray-300 whitespace-pre-wrap">
              这个小项目我的毕业小设计，肯定存在许多逻辑设计问题或bug，有的功能设计思路甚至都是我凭空想象出来的，如有建议请务必联系我，我会尽力吸纳改正的，等毕业答辩结束后我会将完整源码在github上公开，感谢使用！
            </p>
            <div className="mt-6 flex justify-end">
              <button
                type="button"
                onClick={() => setIsAboutModalOpen(false)}
                className="px-4 py-2 rounded-full bg-gray-900 text-white dark:bg-white dark:text-black text-sm font-medium hover:bg-black dark:hover:bg-gray-200 transition-colors"
              >
                我知道了
              </button>
            </div>
          </div>
        </div>
      )}

      {isContactModalOpen && (
        <div className="fixed inset-0 z-[120] flex items-center justify-center p-4">
          <div className="absolute inset-0 bg-black/45 backdrop-blur-[2px]" onClick={() => setIsContactModalOpen(false)}></div>
          <div className="relative w-full max-w-lg rounded-2xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 shadow-2xl p-6 md:p-7 animate-in fade-in zoom-in-95 duration-200">
            <div className="flex items-start justify-between gap-4 mb-4">
              <h3 className="text-xl md:text-2xl font-bold text-gray-900 dark:text-white">联系方式</h3>
              <button
                type="button"
                onClick={() => setIsContactModalOpen(false)}
                className="p-2 rounded-lg text-gray-500 hover:text-gray-900 dark:text-gray-400 dark:hover:text-white hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors"
                aria-label="关闭"
              >
                <X size={18} />
              </button>
            </div>
            <p className="text-sm md:text-base leading-relaxed text-gray-700 dark:text-gray-300 whitespace-pre-wrap">
              微信号：gjl031023{"\n"}邮箱：gjl15502246686@163.com{"\n"}instagram：joker_20031023{"\n"}X：imagine47852854
            </p>
            <div className="mt-6 flex justify-end">
              <button
                type="button"
                onClick={() => setIsContactModalOpen(false)}
                className="px-4 py-2 rounded-full bg-gray-900 text-white dark:bg-white dark:text-black text-sm font-medium hover:bg-black dark:hover:bg-gray-200 transition-colors"
              >
                我知道了
              </button>
            </div>
          </div>
        </div>
      )}

      {activeLegalModal && (
        <div className="fixed inset-0 z-[120] flex items-center justify-center p-4">
          <div className="absolute inset-0 bg-black/45 backdrop-blur-[2px]" onClick={() => setActiveLegalModal('')}></div>
          <div className="relative w-full max-w-lg rounded-2xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 shadow-2xl p-6 md:p-7 animate-in fade-in zoom-in-95 duration-200">
            <div className="flex items-start justify-between gap-4 mb-4">
              <h3 className="text-xl md:text-2xl font-bold text-gray-900 dark:text-white">{activeLegalModal}</h3>
              <button
                type="button"
                onClick={() => setActiveLegalModal('')}
                className="p-2 rounded-lg text-gray-500 hover:text-gray-900 dark:text-gray-400 dark:hover:text-white hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors"
                aria-label="关闭"
              >
                <X size={18} />
              </button>
            </div>
            <p className="text-sm md:text-base leading-relaxed text-gray-700 dark:text-gray-300 whitespace-pre-wrap">
              暂时还没想好，只是占个位嘿嘿
            </p>
            <div className="mt-6 flex justify-end">
              <button
                type="button"
                onClick={() => setActiveLegalModal('')}
                className="px-4 py-2 rounded-full bg-gray-900 text-white dark:bg-white dark:text-black text-sm font-medium hover:bg-black dark:hover:bg-gray-200 transition-colors"
              >
                我知道了
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default LandingPage;
