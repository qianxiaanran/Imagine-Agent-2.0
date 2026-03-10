import React, { useState, useEffect } from 'react';
import {
  Bot,
  Menu,
  X,
  Sun,
  Moon,
  ArrowRight,
  Sparkles,
  CheckCircle2,
  Upload,
  MessageSquare,
  Database,
  ScanText,
  Mic,
  ClipboardCheck,
  Share2,
  Lightbulb,
  Rocket,
  ChevronDown,
} from 'lucide-react';
import Button from '../components/Button';
import { useTheme } from '../context/themeContextValue';
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

const quickSteps = [
  {
    title: '登录并创建会话',
    desc: '进入工作台后点击“新聊天”，默认就是通用企业问答模式。',
    icon: MessageSquare,
    tip: '建议先从一个真实业务问题开始。',
  },
  {
    title: '按任务切换模式',
    desc: '可切换到数据库、联网搜索、会议纪要、OCR、审单、写作等能力面板。',
    icon: Rocket,
    tip: '同一个会话里也能逐步切换处理链路。',
  },
  {
    title: '上传你的材料',
    desc: '支持文档、图片/PDF、音频文件上传，系统会自动做解析和上下文接入。',
    icon: Upload,
    tip: '上传后再提问，回答会更贴近你的业务语境。',
  },
  {
    title: '生成结果并二次加工',
    desc: '可继续追问、编辑、导出、保存上下文，也能走报告/PPT/邮件生成流程。',
    icon: Lightbulb,
    tip: '复杂任务建议拆成两三步，效果通常更稳。',
  },
  {
    title: '分享或进入审单流程',
    desc: '会话可一键分享；单据场景可发起审单任务并跟踪风险等级。',
    icon: Share2,
    tip: '协作前建议先做一次人工复核。',
  },
];

const promptCards = [
  {
    title: '知识库问答',
    icon: MessageSquare,
    text: '请根据我上传的制度文件，提炼“采购审批”流程，并列出每个节点需要的材料。',
  },
  {
    title: '数据库分析',
    icon: Database,
    text: '统计最近三个月每周新增客户和成交额，并指出波动最大的两周。',
  },
  {
    title: 'OCR 录入',
    icon: ScanText,
    text: '识别这份发票中的关键信息，并按“发票号/金额/开票日期/供应商”结构输出。',
  },
  {
    title: '会议纪要',
    icon: Mic,
    text: '把这段会议转写整理成纪要，按“结论、行动项、负责人、截止时间”格式给我。',
  },
  {
    title: '审单场景',
    icon: ClipboardCheck,
    text: '对这份付款申请做风险审查，标注高风险条目并给出复核建议。',
  },
];

const faqs = [
  {
    question: '我需要先上传资料再提问吗？',
    answer: '不是必须。通用问答可以直接开始，但涉及公司制度、合同、单据这类场景时，先上传资料会明显提升准确度。',
  },
  {
    question: '数据库查询会直接执行吗？',
    answer: '会走你当前项目里的数据库查询链路。建议在测试库先验证问题模板，再用于正式业务。',
  },
  {
    question: '哪些结果适合直接分享？',
    answer: '流程说明、纪要摘要、非敏感分析结论适合分享。涉及隐私或财务核心数据时，建议仅在内部会话查看。',
  },
];

const QuickStartPage = ({ onOpenLogin }) => {
  const [isScrolled, setIsScrolled] = useState(false);
  const [isMobileMenuOpen, setIsMobileMenuOpen] = useState(false);
  const [openFaq, setOpenFaq] = useState(0);
  const { toggleTheme, currentTheme } = useTheme();

  useEffect(() => {
    const handleScroll = () => setIsScrolled(window.scrollY > 20);
    window.addEventListener('scroll', handleScroll);
    return () => window.removeEventListener('scroll', handleScroll);
  }, []);

  const navLinks = [
    { name: '首页', href: '/' },
    { name: '能力详情', href: '/capabilities' },
    { name: '操作步骤', href: '#steps' },
    { name: '常见问题', href: '#faq' },
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
            <Button variant="primary" className="!px-5 !py-2 !text-sm !shadow-md" onClick={onOpenLogin}>进入工作台</Button>
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
        <div className="absolute top-0 inset-x-0 h-[760px] bg-[radial-gradient(ellipse_80%_50%_at_50%_-20%,rgba(59,130,246,0.15),rgba(255,255,255,0))] dark:bg-[radial-gradient(ellipse_80%_50%_at_50%_-20%,rgba(59,130,246,0.25),rgba(0,0,0,0))]" />
        <div className="absolute top-36 left-10 w-[360px] h-[360px] bg-blue-50/70 dark:bg-blue-900/20 rounded-full blur-3xl -z-10 opacity-70"></div>

        <div className="max-w-5xl mx-auto px-4 text-center relative z-10">
          <Reveal>
            <SectionBadge>快速上手</SectionBadge>
          </Reveal>
          <Reveal delay={120}>
            <h1 className="text-4xl md:text-6xl font-bold tracking-tight text-gray-900 dark:text-white mb-6 leading-[1.14]">
              10 分钟，把你的第一个业务流程跑通
            </h1>
          </Reveal>
          <Reveal delay={220}>
            <p className="text-lg text-gray-500 dark:text-gray-400 max-w-3xl mx-auto leading-relaxed">
              页面很多、能力也不少，不知道从哪下手很正常。你可以按下面的顺序直接走一遍，基本就能把系统用起来。
            </p>
          </Reveal>
          <Reveal delay={300}>
            <div className="mt-9 flex flex-col sm:flex-row gap-3 justify-center">
              <Button variant="primary" className="text-base px-7 py-3" icon={ArrowRight} onClick={onOpenLogin}>登录并开始</Button>
              <Button variant="outline" className="text-base px-7 py-3" onClick={() => { window.location.href = '/capabilities'; }}>先看能力详情</Button>
            </div>
          </Reveal>
        </div>
      </section>

      <section id="steps" className="py-20 bg-gray-50/60 dark:bg-gray-900/50">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <Reveal>
            <div className="text-center mb-14">
              <SectionBadge>操作步骤</SectionBadge>
              <h2 className="text-3xl md:text-4xl font-bold text-gray-900 dark:text-white mb-4">建议按这个顺序体验</h2>
              <p className="text-gray-500 dark:text-gray-400 max-w-2xl mx-auto">每一步都对应你当前系统已有入口，不需要安装额外插件。</p>
            </div>
          </Reveal>

          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            {quickSteps.map((step, idx) => (
              <Reveal key={step.title} delay={idx * 80}>
                <div className="rounded-[1.75rem] border border-gray-100 dark:border-gray-700 bg-white dark:bg-gray-800 p-6 shadow-sm hover:shadow-xl transition-all duration-300 h-full">
                  <div className="flex items-center justify-between mb-4">
                    <div className="w-11 h-11 rounded-2xl bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-200 flex items-center justify-center">
                      <step.icon size={21} />
                    </div>
                    <span className="text-xs font-semibold text-gray-400">STEP {idx + 1}</span>
                  </div>
                  <h3 className="text-xl font-bold text-gray-900 dark:text-white mb-2">{step.title}</h3>
                  <p className="text-sm text-gray-500 dark:text-gray-400 leading-relaxed mb-4">{step.desc}</p>
                  <div className="text-xs text-gray-600 dark:text-gray-300 bg-gray-50 dark:bg-gray-900/70 border border-gray-100 dark:border-gray-700 rounded-xl px-3 py-2.5">
                    {step.tip}
                  </div>
                </div>
              </Reveal>
            ))}
          </div>
        </div>
      </section>

      <section className="py-20 bg-white dark:bg-gray-950">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 grid lg:grid-cols-2 gap-8 items-start">
          <Reveal>
            <div className="rounded-3xl border border-gray-100 dark:border-gray-800 bg-white dark:bg-gray-900 p-7 shadow-sm">
              <h3 className="text-2xl font-bold text-gray-900 dark:text-white mb-4">推荐提问模板</h3>
              <div className="space-y-3">
                {promptCards.map((card) => (
                  <div key={card.title} className="rounded-2xl border border-gray-100 dark:border-gray-800 px-4 py-3 bg-gray-50/80 dark:bg-gray-800/60">
                    <div className="flex items-center gap-2 text-sm font-semibold text-gray-800 dark:text-gray-200 mb-1.5">
                      <card.icon size={15} className="text-gray-500" />
                      {card.title}
                    </div>
                    <div className="text-sm text-gray-600 dark:text-gray-400 leading-relaxed">{card.text}</div>
                  </div>
                ))}
              </div>
            </div>
          </Reveal>

          <Reveal delay={120}>
            <div className="rounded-3xl border border-gray-100 dark:border-gray-800 bg-white dark:bg-gray-900 p-7 shadow-sm">
              <h3 className="text-2xl font-bold text-gray-900 dark:text-white mb-4">上线前检查清单</h3>
              <div className="space-y-3">
                {[
                  '已完成账号登录与角色检查',
                  '数据库模式仅连接测试库或已控权限库',
                  'OCR 与审单场景已准备样例文件',
                  '语音文件格式与大小可被当前服务处理',
                  '对外分享前已做敏感信息复核',
                ].map((item) => (
                  <div key={item} className="flex items-start gap-2 text-sm text-gray-600 dark:text-gray-300">
                    <CheckCircle2 size={16} className="text-emerald-500 mt-0.5 flex-shrink-0" />
                    <span>{item}</span>
                  </div>
                ))}
              </div>

              <div className="mt-6 rounded-2xl border border-blue-100 dark:border-blue-800 bg-blue-50/70 dark:bg-blue-900/20 px-4 py-3 text-sm text-blue-700 dark:text-blue-300 leading-relaxed">
                小建议：第一次使用时，别把目标定太大。先拿一个“可验证”的小任务跑通，再扩展到完整流程，成功率会更高。
              </div>
            </div>
          </Reveal>
        </div>
      </section>

      <section id="faq" className="py-20 bg-gray-50/60 dark:bg-gray-900/50">
        <div className="max-w-4xl mx-auto px-4">
          <Reveal>
            <div className="text-center mb-10">
              <SectionBadge>常见问题</SectionBadge>
              <h2 className="text-3xl md:text-4xl font-bold text-gray-900 dark:text-white">刚开始最常问的三件事</h2>
            </div>
          </Reveal>

          <div className="space-y-3">
            {faqs.map((item, idx) => {
              const isOpen = openFaq === idx;
              return (
                <Reveal key={item.question} delay={idx * 80}>
                  <button
                    type="button"
                    className="w-full text-left rounded-2xl border border-gray-100 dark:border-gray-800 bg-white dark:bg-gray-900 px-5 py-4 shadow-sm"
                    onClick={() => setOpenFaq(isOpen ? -1 : idx)}
                  >
                    <div className="flex items-center justify-between gap-3">
                      <span className="font-semibold text-gray-900 dark:text-white">{item.question}</span>
                      <ChevronDown size={18} className={`text-gray-400 transition-transform ${isOpen ? 'rotate-180' : ''}`} />
                    </div>
                    {isOpen && (
                      <div className="mt-3 text-sm text-gray-600 dark:text-gray-400 leading-relaxed">
                        {item.answer}
                      </div>
                    )}
                  </button>
                </Reveal>
              );
            })}
          </div>

          <Reveal delay={260}>
            <div className="mt-12 text-center">
              <Button variant="primary" className="text-base px-8 py-3" icon={ArrowRight} onClick={onOpenLogin}>现在登录，开始实际体验</Button>
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
              <p className="text-sm text-gray-500 dark:text-gray-400">快速上手指南，面向当前版本能力。</p>
            </div>
            <div className="flex flex-wrap items-center gap-4 text-sm text-gray-500 dark:text-gray-400">
              <a href="/" className="hover:text-black dark:hover:text-white transition-colors">返回首页</a>
              <a href="/capabilities" className="hover:text-black dark:hover:text-white transition-colors">能力详情</a>
              <button onClick={onOpenLogin} className="hover:text-black dark:hover:text-white transition-colors">登录体验</button>
              <span className="inline-flex items-center gap-1.5 text-xs"><span className="w-2 h-2 rounded-full bg-green-500"></span>系统运行正常</span>
            </div>
          </div>
        </div>
      </footer>
    </div>
  );
};

export default QuickStartPage;
