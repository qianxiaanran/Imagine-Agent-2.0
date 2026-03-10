import React, { useState, useEffect } from 'react';
import {
  Bot,
  Menu,
  X,
  Sun,
  Moon,
  ArrowRight,
  FileText,
  Database,
  Mic,
  ScanText,
  ClipboardCheck,
  Presentation,
  Mail,
  Globe,
  BookOpen,
  Share2,
  ShieldCheck,
  Server,
  CheckCircle2,
  Sparkles,
} from 'lucide-react';
import Button from '../components/Button';
import { useTheme } from '../context/ThemeContext';
import useReveal from '../hooks/useReveal';

const SectionBadge = ({ children }) => (
  <div className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-gray-50 border border-gray-200 text-xs font-bold text-gray-600 uppercase tracking-wider mb-6 dark:bg-gray-800 dark:border-gray-700 dark:text-gray-300">
    <Sparkles size={12} className="text-blue-500" />
    {children}
  </div>
);

const Reveal = ({ children, className = '', delay = 0 }) => {
  const { ref, className: revealClass, style } = useReveal(delay);
  return (
    <div ref={ref} className={`${revealClass} ${className}`} style={style}>
      {children}
    </div>
  );
};


const capabilityModules = [
  {
    title: '对话与知识检索',
    description: '支持通用问答、知识库引用、联网搜索，回答可回溯上下文并保留会话历史。',
    features: ['多轮对话', '知识库问答', '联网搜索模式', '历史会话管理'],
    icon: BookOpen,
    accent: 'from-blue-500/15 to-transparent',
  },
  {
    title: '数据库自然语言查询',
    description: '在数据库模式下直接提问业务问题，系统自动生成并执行 SQL，再把结果解释成可读结论。',
    features: ['Chat to SQL', '结果可解释', '模式切换快捷入口', '上下文连续提问'],
    icon: Database,
    accent: 'from-purple-500/15 to-transparent',
  },
  {
    title: '语音会议与纪要',
    description: '支持录音上传、即时语音输入、纪要整理与继续追问，形成可复用会议记录。',
    features: ['音频上传转写', '即时语音识别', '纪要生成', '会话内追问'],
    icon: Mic,
    accent: 'from-red-500/15 to-transparent',
  },
  {
    title: 'OCR 与结构化录入',
    description: '支持图片/PDF 文本识别、校对编辑、结构化解析以及回写业务数据。',
    features: ['OCR 识别', '文本匹配预览', '结构化解析', '数据录入'],
    icon: ScanText,
    accent: 'from-amber-500/15 to-transparent',
  },
  {
    title: '审单与风控流程',
    description: '发票、合同、付款类单据可发起审单任务，支持进度追踪、风险分级与ERP动作。',
    features: ['审单任务队列', '风险分级', '进度轮询', 'ERP动作接口'],
    icon: ClipboardCheck,
    accent: 'from-emerald-500/15 to-transparent',
  },
  {
    title: '写作与成果分发',
    description: '内置报告、PPT、邮件写作面板，支持结构化结果输出和会话分享链接。',
    features: ['报告生成', 'PPT 大纲', '邮件草稿', '分享会话链接'],
    icon: Presentation,
    accent: 'from-cyan-500/15 to-transparent',
  },
];

const integrationRows = [
  {
    layer: '前端交互',
    detail: 'React + Vite + Tailwind 页面体系，支持多模式对话、文件上传、预览与设置。',
    status: '已接入',
    icon: Bot,
  },
  {
    layer: 'API 网关',
    detail: 'FastAPI 统一入口，覆盖 chat、history、ocr、voice、audit、share、admin 等接口。',
    status: '已接入',
    icon: Globe,
  },
  {
    layer: '模型与检索',
    detail: '本地模型与云模型双后端切换，结合向量检索与关键词策略进行问答。',
    status: '已接入',
    icon: Server,
  },
  {
    layer: '安全与权限',
    detail: '登录态校验、账户状态管控、管理后台角色操作，支持私有化部署路径。',
    status: '已接入',
    icon: ShieldCheck,
  },
];

const CapabilitiesPage = ({ onOpenLogin }) => {
  const [isScrolled, setIsScrolled] = useState(false);
  const [isMobileMenuOpen, setIsMobileMenuOpen] = useState(false);
  const { toggleTheme, currentTheme } = useTheme();

  useEffect(() => {
    const handleScroll = () => setIsScrolled(window.scrollY > 20);
    window.addEventListener('scroll', handleScroll);
    return () => window.removeEventListener('scroll', handleScroll);
  }, []);

  const navLinks = [
    { name: '首页', href: '/' },
    { name: '能力总览', href: '#modules' },
    { name: '集成清单', href: '#integrations' },
    { name: '快速上手', href: '/quickstart' },
  ];

  return (
    <div
      className="min-h-screen bg-white dark:bg-gray-950 font-sans text-gray-900 dark:text-gray-100 selection:bg-gray-900 selection:text-white dark:selection:bg-white dark:selection:text-black overflow-x-hidden animate-in fade-in duration-500 transition-colors"
      style={{ minHeight: 'var(--app-height, 100vh)' }}
    >
      <nav className={`fixed top-0 left-0 right-0 z-50 transition-all duration-300 ${isScrolled ? 'bg-white/90 dark:bg-gray-950/90 backdrop-blur-xl border-b border-gray-100 dark:border-gray-800 py-3 shadow-sm' : 'bg-transparent py-5'}`}>
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 flex justify-between items-center">
          <a href="/" className="flex items-center gap-2.5 group">
            <div className="w-9 h-9 bg-gray-900 dark:bg-white rounded-xl flex items-center justify-center text-white dark:text-black shadow-lg shadow-gray-900/20 group-hover:scale-105 transition-transform duration-300">
              <Bot size={20} />
            </div>
            <span className="text-lg font-bold tracking-tight text-gray-900 dark:text-white">企业智能办公</span>
          </a>

          <div className="hidden md:flex items-center gap-8 bg-gray-50/80 dark:bg-gray-800/80 px-6 py-2 rounded-full border border-gray-100/50 dark:border-gray-700/50 backdrop-blur-sm">
            {navLinks.map((link) => (
              <a key={link.name} href={link.href} className="text-sm font-medium text-gray-500 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white transition-colors relative group">
                {link.name}
                <span className="absolute -bottom-1 left-0 w-0 h-0.5 bg-gray-900 dark:bg-white transition-all duration-300 group-hover:w-full"></span>
              </a>
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
            <Button variant="primary" className="!px-5 !py-2 !text-sm !shadow-md" onClick={onOpenLogin}>立即体验</Button>
          </div>

          <button className="md:hidden p-2 text-gray-600 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-800 rounded-lg transition-colors" onClick={() => setIsMobileMenuOpen(!isMobileMenuOpen)}>
            {isMobileMenuOpen ? <X size={24} /> : <Menu size={24} />}
          </button>
        </div>

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

      <section className="relative pt-32 pb-20 lg:pt-44 lg:pb-24 overflow-hidden">
        <div className="absolute top-0 inset-x-0 h-[760px] bg-[radial-gradient(ellipse_80%_50%_at_50%_-20%,rgba(37,99,235,0.16),rgba(255,255,255,0))] dark:bg-[radial-gradient(ellipse_80%_50%_at_50%_-20%,rgba(59,130,246,0.28),rgba(0,0,0,0))]" />
        <div className="absolute top-40 right-0 w-[460px] h-[460px] bg-blue-50/60 dark:bg-blue-900/20 rounded-full blur-3xl -z-10 opacity-70"></div>

        <div className="max-w-6xl mx-auto px-4 text-center relative z-10">
          <Reveal>
            <SectionBadge>能力地图</SectionBadge>
          </Reveal>
          <Reveal delay={120}>
            <h1 className="text-4xl md:text-6xl font-bold tracking-tight text-gray-900 dark:text-white mb-6 leading-[1.14]">
              你现在能直接用上的功能，<br className="hidden md:block" />都在这里
            </h1>
          </Reveal>
          <Reveal delay={220}>
            <p className="text-lg text-gray-500 dark:text-gray-400 max-w-3xl mx-auto leading-relaxed">
              这不是“未来规划页”，而是按你当前项目代码和接口梳理的能力清单。对话、文档、数据库、语音、OCR、审单、写作与分享能力都已经串起来了。
            </p>
          </Reveal>
          <Reveal delay={300}>
            <div className="mt-10 flex flex-wrap justify-center gap-3">
              {[
                { icon: FileText, text: '文档 + OCR 处理链路' },
                { icon: Database, text: '数据库自然语言查询' },
                { icon: ClipboardCheck, text: '审单任务与风控回路' },
                { icon: Share2, text: '会话分享与协同' },
              ].map((item) => (
                <div key={item.text} className="inline-flex items-center gap-2 px-4 py-2 rounded-full border border-gray-200 dark:border-gray-700 bg-white/90 dark:bg-gray-900/70 text-sm text-gray-600 dark:text-gray-300 shadow-sm">
                  <item.icon size={15} className="text-gray-500 dark:text-gray-400" />
                  {item.text}
                </div>
              ))}
            </div>
          </Reveal>
        </div>
      </section>

      <section id="modules" className="py-20 bg-gray-50/60 dark:bg-gray-900/50">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <Reveal>
            <div className="text-center mb-14">
              <SectionBadge>模块能力</SectionBadge>
              <h2 className="text-3xl md:text-4xl font-bold text-gray-900 dark:text-white mb-4">按场景拆解后的能力模块</h2>
              <p className="text-gray-500 dark:text-gray-400 max-w-2xl mx-auto">每个模块都可以在现有 Dashboard 中找到入口，不需要额外开新系统。</p>
            </div>
          </Reveal>

          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            {capabilityModules.map((item, idx) => (
              <Reveal key={item.title} delay={idx * 80} className="h-full">
                <div className="h-full rounded-[1.75rem] border border-gray-100 dark:border-gray-700 bg-white dark:bg-gray-800 p-6 shadow-sm hover:shadow-xl transition-all duration-300 group relative overflow-hidden">
                  <div className={`absolute inset-0 bg-gradient-to-br ${item.accent} opacity-0 group-hover:opacity-100 transition-opacity`}></div>
                  <div className="relative z-10 h-full flex flex-col">
                    <div className="w-12 h-12 rounded-2xl bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-200 flex items-center justify-center mb-4 group-hover:scale-110 transition-transform">
                      <item.icon size={22} />
                    </div>
                    <h3 className="text-xl font-bold text-gray-900 dark:text-white mb-2">{item.title}</h3>
                    <p className="text-sm text-gray-500 dark:text-gray-400 leading-relaxed mb-4">{item.description}</p>
                    <div className="mt-auto space-y-2">
                      {item.features.map((feature) => (
                        <div key={feature} className="flex items-center gap-2 text-xs text-gray-600 dark:text-gray-300">
                          <CheckCircle2 size={14} className="text-emerald-500 flex-shrink-0" />
                          <span>{feature}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                </div>
              </Reveal>
            ))}
          </div>
        </div>
      </section>

      <section id="integrations" className="py-20 bg-white dark:bg-gray-950">
        <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8">
          <Reveal>
            <div className="text-center mb-12">
              <SectionBadge>集成清单</SectionBadge>
              <h2 className="text-3xl md:text-4xl font-bold text-gray-900 dark:text-white mb-4">从前端到服务层的落地状态</h2>
              <p className="text-gray-500 dark:text-gray-400">这里列的是当前仓库里已经接上的能力层，不含“仅计划中”项目。</p>
            </div>
          </Reveal>

          <Reveal delay={120}>
            <div className="rounded-3xl border border-gray-100 dark:border-gray-800 bg-white dark:bg-gray-900 shadow-sm overflow-hidden">
              {integrationRows.map((row, idx) => (
                <div key={row.layer} className={`px-6 py-5 flex flex-col md:flex-row md:items-center md:justify-between gap-3 ${idx < integrationRows.length - 1 ? 'border-b border-gray-100 dark:border-gray-800' : ''}`}>
                  <div className="flex items-start gap-3">
                    <div className="w-9 h-9 rounded-xl bg-gray-100 dark:bg-gray-800 flex items-center justify-center text-gray-600 dark:text-gray-300 mt-0.5">
                      <row.icon size={18} />
                    </div>
                    <div>
                      <div className="text-sm font-semibold text-gray-900 dark:text-white">{row.layer}</div>
                      <div className="text-sm text-gray-500 dark:text-gray-400 mt-1 leading-relaxed">{row.detail}</div>
                    </div>
                  </div>
                  <span className="inline-flex items-center justify-center px-3 py-1 rounded-full text-xs font-semibold border border-emerald-200 bg-emerald-50 text-emerald-600 dark:border-emerald-800 dark:bg-emerald-900/30 dark:text-emerald-300">
                    {row.status}
                  </span>
                </div>
              ))}
            </div>
          </Reveal>
        </div>
      </section>

      <section className="py-20 bg-gray-50/60 dark:bg-gray-900/50">
        <div className="max-w-5xl mx-auto px-4 text-center">
          <Reveal>
            <SectionBadge>开始使用</SectionBadge>
            <h2 className="text-3xl md:text-4xl font-bold text-gray-900 dark:text-white mb-4">先登录，再按场景开启对应能力</h2>
            <p className="text-gray-500 dark:text-gray-400 mb-8 max-w-2xl mx-auto">
              如果你想看完整操作路径，可以先走一遍快速上手页；要直接试功能，现在登录就行。
            </p>
            <div className="flex flex-col sm:flex-row gap-3 justify-center">
              <Button variant="primary" className="text-base px-7 py-3" icon={ArrowRight} onClick={onOpenLogin}>登录并进入工作台</Button>
              <Button variant="outline" className="text-base px-7 py-3" onClick={() => { window.location.href = '/quickstart'; }}>查看快速上手</Button>
            </div>
          </Reveal>
        </div>
      </section>

      <footer className="bg-white dark:bg-gray-950 border-t border-gray-100 dark:border-gray-800 pt-16 pb-10">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex flex-col md:flex-row items-start md:items-center justify-between gap-6">
            <div>
              <div className="flex items-center gap-2.5 mb-2">
                <div className="w-8 h-8 bg-gray-900 dark:bg-white rounded-lg flex items-center justify-center text-white dark:text-black"><Bot size={18} /></div>
                <span className="font-bold text-lg text-gray-900 dark:text-white">企业智能办公</span>
              </div>
              <p className="text-sm text-gray-500 dark:text-gray-400">按真实代码能力组织的功能落地页。</p>
            </div>
            <div className="flex flex-wrap items-center gap-4 text-sm text-gray-500 dark:text-gray-400">
              <a href="/" className="hover:text-black dark:hover:text-white transition-colors">返回首页</a>
              <a href="/quickstart" className="hover:text-black dark:hover:text-white transition-colors">快速上手</a>
              <button onClick={onOpenLogin} className="hover:text-black dark:hover:text-white transition-colors">登录体验</button>
              <span className="inline-flex items-center gap-1.5 text-xs"><span className="w-2 h-2 rounded-full bg-green-500"></span>系统运行正常</span>
            </div>
          </div>
        </div>
      </footer>
    </div>
  );
};

export default CapabilitiesPage;
