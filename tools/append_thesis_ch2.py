from __future__ import annotations

import zipfile
import xml.etree.ElementTree as ET
from copy import deepcopy
from pathlib import Path


W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
XML_NS = "http://www.w3.org/XML/1998/namespace"

ET.register_namespace("w", W_NS)
ET.register_namespace("r", "http://schemas.openxmlformats.org/officeDocument/2006/relationships")
ET.register_namespace("wp", "http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing")
ET.register_namespace("a", "http://schemas.openxmlformats.org/drawingml/2006/main")
ET.register_namespace("wps", "http://schemas.microsoft.com/office/word/2010/wordprocessingShape")
ET.register_namespace("w14", "http://schemas.microsoft.com/office/word/2010/wordml")
ET.register_namespace("mc", "http://schemas.openxmlformats.org/markup-compatibility/2006")
ET.register_namespace("v", "urn:schemas-microsoft-com:vml")
ET.register_namespace("o", "urn:schemas-microsoft-com:office:office")


def qn(tag: str) -> str:
    return f"{{{W_NS}}}{tag}"


def paragraph_text(para: ET.Element) -> str:
    return "".join(node.text or "" for node in para.iter(qn("t")))


def get_body_paragraphs(body: ET.Element) -> list[ET.Element]:
    return [child for child in body if child.tag == qn("p")]


def clear_paragraph(para: ET.Element) -> None:
    ppr = para.find(qn("pPr"))
    for child in list(para):
        if child is not ppr:
            para.remove(child)


def clone_rpr(run: ET.Element | None) -> ET.Element | None:
    if run is None:
        return None
    rpr = run.find(qn("rPr"))
    if rpr is None:
        return None
    return deepcopy(rpr)


def make_run(text: str, template_run: ET.Element | None) -> ET.Element:
    run = ET.Element(qn("r"))
    rpr = clone_rpr(template_run)
    if rpr is not None:
        run.append(rpr)
    t = ET.SubElement(run, qn("t"))
    if text.startswith(" ") or text.endswith(" ") or "  " in text:
        t.set(f"{{{XML_NS}}}space", "preserve")
    t.text = text
    return run


def set_paragraph_text(para: ET.Element, text: str, template_run: ET.Element | None) -> None:
    clear_paragraph(para)
    para.append(make_run(text, template_run))


def make_page_break_paragraph(template_para: ET.Element, template_run: ET.Element | None) -> ET.Element:
    para = deepcopy(template_para)
    clear_paragraph(para)
    run = ET.Element(qn("r"))
    rpr = clone_rpr(template_run)
    if rpr is not None:
        run.append(rpr)
    br = ET.SubElement(run, qn("br"))
    br.set(qn("type"), "page")
    para.append(run)
    return para


def find_paragraph_by_exact_text(paras: list[ET.Element], target: str) -> ET.Element:
    for para in paras:
        if paragraph_text(para).strip() == target:
            return para
    raise RuntimeError(f"Paragraph not found: {target}")


def insert_paragraphs_before(
    body: ET.Element,
    anchor: ET.Element,
    template_para: ET.Element,
    template_run: ET.Element | None,
    texts: list[str],
) -> list[ET.Element]:
    inserted: list[ET.Element] = []
    base_index = list(body).index(anchor)
    for offset, text in enumerate(texts):
        para = deepcopy(template_para)
        set_paragraph_text(para, text, template_run)
        body.insert(base_index + offset, para)
        inserted.append(para)
    return inserted


def insert_before_sectpr(body: ET.Element, paragraphs: list[ET.Element]) -> None:
    children = list(body)
    sectpr_index = next((idx for idx, child in enumerate(children) if child.tag == qn("sectPr")), len(children))
    for offset, para in enumerate(paragraphs):
        body.insert(sectpr_index + offset, para)


def section(title: str, paragraphs: list[str]) -> dict[str, object]:
    return {"title": title, "paragraphs": paragraphs}


def make_chapter_content() -> dict[str, object]:
    toc = [
        "2 开发工具及相关技术简介 ......................................... 15",
        "2.1 系统开发环境与工具选择 ....................................... 15",
        "2.2 前端界面构建与交互实现技术 ................................... 18",
        "2.3 后端服务框架与接口组织技术 ................................... 22",
        "2.4 数据持久化、对象存储与会话管理技术 ............................. 27",
        "2.5 大语言模型接入与检索增强生成技术 ............................... 32",
        "2.6 OCR、语音与多模态处理技术 .................................... 38",
        "2.7 本章小结 ..................................................... 44",
    ]

    sections = [
        section(
            "系统开发环境与工具选择",
            [
                "第二章的任务并不是重复介绍系统的功能现象，而是从工程实现视角说明本系统赖以成立的开发工具、技术框架与关键支撑机制。对于企业智能办公助手而言，系统成败并不取决于某一个模型接口是否可调用，而取决于前端工作台、后端服务、数据平台、检索链路、多模态处理能力与外部工具集成方式能否被组织成稳定、可扩展、可维护的整体。因此，本章将结合项目源码与已落地模块，系统梳理 Enterprise Intelligent Office Agent 2.0 的技术基础，并说明相应工具选择背后的工程逻辑。",
                "从项目特征来看，该系统同时具备多模态输入、知识检索、数据库问答、会议转写、审单分析、写作生成和管理后台等复合能力。这意味着系统既要面对高并发的前后端交互，又要兼容文档解析、向量计算、OCR 推理、语音识别和第三方服务调用等异构任务。若技术选型偏向单一场景，往往会在扩展阶段暴露出接口耦合严重、运行链路冗长、跨模块状态难以维护等问题。因此，本项目在工具选择上遵循四项原则：一是优先采用生态成熟、社区活跃的开源框架；二是优先支持本地部署与二次开发；三是优先保证模块边界清晰、便于后期扩展；四是优先兼顾开发效率与企业场景下的可治理性。",
                "在前端开发环境方面，项目选用了以 React 19.2.0 为核心的现代 Web 技术栈，并采用 Vite 7.2.4 作为构建与开发服务器。React 的组件化思想适合构建复杂办公工作台，能够将登录、仪表盘、审单后台、PPT 工作区、写作工作区、会话侧栏、上传面板等界面拆分为具备复用价值的功能单元。Vite 则以原生 ES Module 为基础，在开发阶段具备启动快、热更新响应迅速和工程配置灵活等优点，尤其适合需要频繁联调前后端接口的大型单页应用。对于本系统这种界面密集、状态切换频繁的办公平台而言，React 与 Vite 的组合可以显著降低开发与调试成本。",
                "在后端开发环境方面，项目采用 Python 生态与 FastAPI 框架。Python 的优势在于能够高效连接大语言模型、向量检索、OCR、语音识别、文档解析和数据库操作等多个 AI 与数据处理工具链，避免在多语言服务之间频繁进行协议转换。FastAPI 则兼具异步接口支持、自动数据校验、OpenAPI 文档生成和路由模块化组织等能力，适合实现聊天流式输出、文件上传、后台任务、权限接口和多模式业务路由。本项目的后端并非传统意义上的单纯 CRUD 服务，而是一个围绕模型调度与内容处理展开的能力编排层，因此选择 FastAPI 具有较高的工程适配性。",
                "在模型运行环境方面，项目采用“本地模型优先、云端模型补充”的双后端策略。源码显示系统通过 Ollama 接入本地大语言模型，默认模型为 qwen2.5-coder，同时保留对 DeepSeek 云端模型的兼容接入。这样的设计并不是简单的冗余，而是出于企业场景下隐私保护、响应成本、推理速度与能力弹性的综合考量。本地模型适合处理对数据安全敏感、需要持续上下文的内部办公任务；云端模型则可以在推理质量、长文本表达或资源弹性方面提供补充。双后端结构使系统能够根据任务类型、部署环境和资源状态动态切换模型后端，增强实际落地的可行性。",
                "在数据与基础设施工具方面，项目使用 Supabase 作为数据库、认证与对象存储的统一支撑平台，并通过 SQLAlchemy 建立 Python 侧的数据库连接管理。Supabase 的优势在于其同时提供 PostgreSQL、对象存储、鉴权和客户端 SDK，使系统能够在较低运维门槛下完成结构化数据、历史会话、知识切片与音频文件的统一管理。结合本项目的本地部署方式，Supabase 还具备较好的私有化适应能力，能够满足企业对内网部署、权限隔离和数据可控的要求。相较于分别拼装多个独立组件，这种平台化基础设施明显降低了系统整合复杂度。",
                "除核心框架外，项目还使用了一系列与办公场景密切相关的支撑工具。例如，前端通过 @supabase/supabase-js 实现浏览器侧鉴权状态与对象存储访问；后端通过 LangChain 系列组件连接检索增强生成链路；通过 PaddleOCR、pdf2image、pydub、sentence-transformers 等库完成文本、图像、PDF 与音频的跨模态处理；通过 Presenton 相关接口完成 PPT 生成服务接入。这些工具并非孤立存在，而是围绕统一业务平台被有机组织，使系统具备从原始材料采集、语义理解到内容生成的连续处理能力。",
                "总体而言，本项目的开发工具选择体现了一种偏工程实用主义的路线：前端强调交互效率与模块化组织，后端强调异步接口与 AI 工具链融合，数据层强调本地可控与统一管理，模型层强调能力弹性与隐私平衡，多模态层强调实际办公资料的可接入性。正是在这种多层协同的工具体系下，企业智能办公助手才不再是演示性质的功能拼接，而具备了面向真实组织流程持续演进的技术基础。",
            ],
        ),
        section(
            "前端界面构建与交互实现技术",
            [
                "前端系统是用户感知智能办公平台能力的第一入口，其质量直接决定模型能力能否被自然、连续地使用。本项目以前端单页应用作为统一工作台，将知识问答、文件上传、会议纪要、数据库查询、智能写作、PPT 生成、审单辅助和后台管理等功能集中到同一界面体系之中。这一设计区别于将多个工具分散部署在不同页面或子系统中的传统方式，目的在于减少用户在复杂办公任务中的界面切换成本，使上下文和任务状态能够在同一交互空间内延续。",
                "从框架层面看，React 为本系统提供了清晰的组件化组织方式。登录页、仪表盘页、管理后台页、审单工作区、会话消息区、上传入口、模型切换控件与状态面板，都可以通过组件封装实现职责分离。组件化的价值不仅体现在代码复用上，更体现在复杂状态的局部收敛上。企业办公系统常常需要同时处理上传状态、流式回复状态、权限状态、会话状态与模态弹窗状态，若没有足够清晰的组件边界，界面逻辑很容易膨胀失控。React 以自上而下的数据流与声明式渲染机制，有效支撑了这类高复杂度界面的开发。",
                "路由层面上，项目使用 React Router 7.9.6 对不同功能页面进行组织，实现了登录、用户主工作台、管理员后台、分享页面等多类场景的切换。由于系统并不仅仅是简单的问答页面，而是带有会话上下文、业务模式和角色权限差异的综合平台，路由设计必须同时关注页面可达性与状态连续性。通过前端路由机制，系统能够在创建新会话、进入某个历史会话、打开分享内容或跳转后台审核页时，保持明确的页面语义和较低的刷新成本。这对于需要长期保存任务上下文的企业办公系统尤为重要。",
                "在工程构建方面，Vite 提供了高效的本地开发能力与更细粒度的构建控制。项目在 vite.config.js 中通过 manualChunks 对登录公共组件、管理后台模块、Markdown 渲染依赖、代码高亮依赖、Supabase SDK 与 React 核心依赖进行分包，使大型前端工程在生产环境下具备更好的首屏加载效率与缓存复用效果。同时，Vite 的本地代理能力还将 /api 请求转发到后端服务，降低了前后端联调时的跨域与部署复杂度。对于一个需要持续迭代的智能办公平台而言，良好的构建效率本身就是提高研发速度的重要条件。",
                "前端与后端的数据交互在本项目中并非简单的表单提交关系，而是带有鉴权与重试逻辑的长链路接口调用。项目中的 apiClient.js 采用基于 fetch 的统一请求封装，对访问令牌、刷新令牌、本地记住登录时间窗和未经授权时的自动处理进行了集中管理。当接口返回 401 状态时，前端会优先尝试通过后端刷新令牌接口或 Supabase SDK 进行会话续期，降低用户在长期使用工作台过程中的中断概率。这种设计使平台更适合真实办公环境下的持续使用，而不是一次性演示。",
                "在云存储与会话协同方面，前端通过 @supabase/supabase-js 接入 Supabase 客户端，实现对象存储桶、身份会话与浏览器侧令牌之间的协同。以音频上传场景为例，用户在浏览器端选择会议录音后，前端既需要将文件正确传给后端发起转写，又要在必要时保留对象存储中的文件引用以供后续回放、结果关联或分享使用。Supabase JS 的引入使前端不必自行维护额外的存储签名机制，降低了文件类能力接入的复杂度。",
                "从界面表现与交互组织角度看，项目采用了以组件样式和工程化 CSS 变量为基础的界面构建方式，并结合 TailwindCSS 相关工具增强样式开发效率。虽然系统功能众多，但前端并未将不同能力简单堆叠，而是通过工作台式布局、侧边栏、状态分区、卡片化入口与上传面板，将“聊天式交互”与“工具式操作”整合在统一界面中。这种设计既保留了大语言模型交互的自然性，又兼顾了企业工具场景中对显式状态、结果留痕和任务入口可见性的需求。",
                "值得注意的是，本项目的前端并未引入过于复杂的全局状态管理框架，而是更多依赖页面级状态、组件状态与接口协作来维持交互逻辑。对于企业智能办公平台而言，这种策略具有一定合理性：其一，可减少额外状态抽象带来的学习成本；其二，便于围绕具体功能模块快速演进；其三，能够让会话、上传、模式切换等高频状态与页面逻辑紧密结合，避免过度工程化。在后期系统继续扩展时，也可以在现有基础上逐步抽离稳定状态模型，而不必在项目早期承担过重的架构负担。",
                "综合来看，前端技术栈在本系统中承担的并不只是“做一个漂亮界面”的职责，而是负责把复杂的模型能力、文件能力和数据能力组织成用户可理解、可操作、可持续追问的办公工作台。React、React Router、Vite 与 Supabase JS 的组合，使平台具备了较强的界面组织能力、接口协同能力与长期维护能力，为系统后续功能拓展和业务模式迭代提供了稳定基础。",
            ],
        ),
        section(
            "后端服务框架与接口组织技术",
            [
                "如果说前端工作台负责承载用户视角下的交互过程，那么后端服务层则负责把看似连续的办公行为拆解为可执行的接口链路、模型调用链路与数据访问链路。本项目选择 FastAPI 作为后端框架，其核心原因在于该框架不仅具备轻量、异步、性能较高等优点，还能够与 Python 的 AI 生态自然衔接。对于一个既需要处理普通 REST 接口，又需要处理流式聊天响应、文件上传、后台线程任务和多模块编排的系统而言，FastAPI 兼顾了开发效率与接口表达能力。",
                "从主程序结构看，系统在 main.py 中采用了较为务实的模块化装配方式。核心路由并不是一次性静态绑定，而是通过可选导入的方式按能力模块加载，包括认证、聊天、审单、管理后台、决策分析、文档处理、语音处理、OCR、PPT 生成与分享管理等。这种组织方式有两个直接好处：其一，在部分依赖尚未就绪或某个模块暂不可用时，主服务仍能以降级方式启动，提升开发与部署过程中的容错性；其二，不同能力可以围绕独立路由持续演进，降低大文件式耦合的风险。",
                "在接口组织层面，本项目充分利用了 FastAPI 的 APIRouter 与 Pydantic 数据模型机制。无论是聊天请求、PPT 生成请求、会话重命名请求，还是音频转写和管理后台相关请求，都通过显式的数据结构进行约束。Pydantic 带来的字段校验、类型提示和结构清晰性，有助于降低前后端协作时的语义歧义，也有利于在复杂业务接口中快速定位问题。相较于依赖自由字典传参的松散风格，这种方式更符合企业系统开发中对接口可维护性的要求。",
                "企业智能办公平台的一项关键特征是流式交互。用户在提出问题之后，并不总是愿意等待完整结果一次性返回，而希望实时看到模型推理与生成过程。本项目在聊天接口中通过 StreamingResponse 实现流式输出，让前端能够逐步渲染模型回答内容。对于长文本写作、知识问答和数据库结果解释等任务，这一机制不仅改善了等待体验，也增强了系统在复杂任务下的可感知性。与传统同步接口相比，流式响应更适合承担“对话式工具调用平台”的核心交互。",
                "后端框架还承担着多模式路由的责任。系统并没有将所有请求简单地送入一个统一模型提示词中处理，而是在聊天路由中根据用户当前模式、文件上下文和业务类型，分别组织数据库问答、文档检索、一般聊天、审单辅助、OCR 上下文总结和会议纪要等不同处理路径。这种“能力路由”思想是企业级智能系统区别于通用聊天机器人的重要特征。它意味着后端不只是一个模型转发器，更是任务理解与工具编排的协调层。",
                "对于需要耗时处理的任务，后端采用后台线程与异步任务结合的方式降低主请求阻塞程度。例如语音转写可以在提交任务后由独立线程继续处理，PPT 生成与轮询查询也通过异步接口和状态查询机制完成，OCR 识别与文档向量化同样可以与主对话流程解耦。这样的设计并没有引入过重的分布式任务系统，而是在当前项目体量下保持了足够实用的并发组织方式，兼顾实现复杂度与使用效果。",
                "此外，项目在后端运行期还设计了启动预热与运行时清理机制。例如系统启动时会根据配置决定是否预热大语言模型、嵌入模型和决策缓存，以降低首次请求延迟；同时会确保运行时静态目录、OCR 临时目录和历史遗留文件迁移逻辑得到执行，避免资源分布混乱。对于办公系统而言，这些“非业务代码”同样重要，因为它们直接影响系统稳定性、长期运行质量与开发维护成本。",
                "综上，本项目的后端并不是以传统 Web 管理系统的思路实现，而是以“AI 能力平台化”视角构建：FastAPI 负责提供高效接口骨架，APIRouter 负责能力模块分治，Pydantic 负责数据结构约束，流式响应负责提升交互连续性，多模式路由负责控制不同任务链路，后台线程和运行时管理负责维持系统稳定。正是这些后端组织技术共同作用，才使前端的统一工作台能够真正联通模型、数据与多模态能力。",
            ],
        ),
        section(
            "数据持久化、对象存储与会话管理技术",
            [
                "企业智能办公系统并不仅仅处理一次性的问答请求，它需要长期保存用户会话、文件内容、结构化数据、知识切片、任务状态与对象文件。因此，数据层设计必须同时覆盖结构化事务数据与非结构化内容资产，既要保证查询与更新效率，又要支持后续检索、追溯和共享。本项目在这一层面采用了 Supabase 平台与 PostgreSQL 数据库相结合的方案，通过统一的数据底座承载聊天会话、业务数据库、向量化文档与对象文件。",
                "在结构化数据访问方面，后端通过 SQLAlchemy 建立与 Supabase PostgreSQL 的连接，使用连接池、预检测与会话工厂等机制组织数据库交互。与许多只把数据库当作普通配置存储的 AI 应用不同，本项目明确包含企业经营类业务表，例如公司信息、部门、角色、员工、客户、供应商、产品、库存、订单、订单明细和采购等 11 张核心业务表。database_manager.py 中通过白名单、表关系描述和关键词映射来约束模型可访问的数据范围，这为自然语言数据库查询能力提供了可靠边界。",
                "历史会话管理是办公平台可持续使用的另一基础。本项目在 history_manager.py 中将用户消息、助手回复和上下文记录持久化到 history 与 session_titles 等表，并实现会话标题生成、分页查询、重命名、删除和历史迁移等逻辑。更重要的是，该模块并不仅满足“能存下来”这一最低要求，还对历史表的自增序列缺失、索引缺失等本地迁移问题进行了自修复处理，并为按用户、按会话、按创建时间的高频查询增加索引。这些细节体现出系统已经考虑到真实运行中的数据库演化问题。",
                "对于非结构化文件，本项目借助 Supabase Storage 提供对象存储能力。目前系统至少使用了 voice_uploads 等存储桶保存会议音频或相关文件，并通过上传、签名链接、二进制读取和后续转写任务建立关联。对象存储的意义不仅在于保存原始文件，更在于把文件生命周期从单次上传请求中解耦出来，使系统能够在转写、分享、历史复盘和后续下载中持续引用同一对象。这种设计比仅将文件保存在临时目录中更适合企业场景。",
                "文档知识库的数据组织则体现了本项目在检索增强方面的工程思路。源码显示，系统会将用户上传的 PDF、DOCX、TXT 等文件经过解析、切分、向量化后写入 documents 表，每个文档切片除正文内容外，还保留文件名、页码、来源、用户 ID 等元数据，并记录对应嵌入向量。这样一来，知识库不再是粗粒度的“文件级存储”，而是面向语义检索的“片段级组织”。对于企业知识问答系统而言，这种粒度控制能够显著提升召回准确率和结果可引用性。",
                "在认证与权限协同方面，Supabase 还承担了浏览器会话与服务端管理的衔接职责。前端通过 @supabase/supabase-js 管理用户登录态与刷新令牌，后端则同时维护匿名客户端和服务端管理员客户端，以分别处理普通用户请求与需要更高权限的存储、管理操作。通过这种前后端分层使用方式，项目避免了将所有能力都暴露在同一安全边界内，有助于后续进一步扩展角色管理、资源隔离与后台治理能力。",
                "为保证数据访问的稳定性与安全性，系统在数据库问答链路中引入了只读校验、表白名单、SQL 语句清洗、结果缓存与摘要缓存等机制。这表明本项目并没有把大语言模型产生的 SQL 直接视为可信结果，而是通过程序性约束对其进行再过滤。类似地，会话管理模块中的分页限制、历史迁移逻辑和索引修复机制，也都体现出一种“先考虑长期运行，再考虑功能表面效果”的工程思路。",
                "总体来看，本项目的数据持久化技术并非单纯依赖某个数据库产品，而是围绕“结构化业务数据、历史会话数据、知识向量数据与对象文件数据”四类核心对象进行分层设计。Supabase 与 PostgreSQL 负责统一承载，SQLAlchemy 负责后端连接组织，会话管理负责连续上下文，存储桶负责多媒体文件生命周期，向量文档表负责语义检索基础。这种数据层设计为系统的多场景协同提供了稳定支撑，也为后续扩展权限控制、审计追踪和组织级知识治理奠定了基础。",
            ],
        ),
        section(
            "大语言模型接入与检索增强生成技术",
            [
                "作为企业智能办公助手的核心能力层，大语言模型决定了系统在自然语言理解、综合分析、摘要归纳和内容生成方面的上限。但在企业场景中，单纯接入一个通用模型远远不够，因为模型若无法访问企业私域知识、数据库结果和任务上下文，其回答往往停留在语言流畅而依据不足的层面。因此，本项目在模型层并没有采用“单模型直连前端”的简单方案，而是围绕模型接入、上下文构造、检索增强和工具协同构建了较为完整的能力体系。",
                "从模型接入方式看，系统在 deepseek_llm.py 中实现了本地 Ollama 模型与云端 DeepSeek 模型的统一封装。默认情况下，本地模型由 Ollama 托管，模型名称配置为 qwen2.5-coder，并结合上下文长度、保活时长、并发限制和 HTTP 流式回退机制组织推理调用；云端模型则通过兼容 OpenAI 风格接口的 ChatOpenAI 封装接入 DeepSeek 服务。这种统一封装方式使前端无需感知模型调用差异，只需通过模型后端参数即可切换本地与云端模式，从而提升系统整体灵活性。",
                "在运行控制层面，项目并没有忽略模型并发与资源占用问题。源码中分别为本地模型和云端模型设置了不同的并发信号量与等待超时机制，避免在多用户或多窗口并发提问时将本地模型资源迅速耗尽。同时，Ollama 相关参数中还配置了上下文长度、GPU 数量、生成长度、保活时间等选项，用于平衡响应速度与内容完整性。可以看出，本项目在模型接入上已经超越“能连上就行”的初级阶段，而开始考虑推理资源治理与用户体验稳定性。",
                "为了使模型输出与企业语境保持一致，系统在聊天链路中构建了较完整的上下文组织机制。chat_router.py 会结合用户消息、会话历史、个性化偏好、OCR 上下文、会议纪要文本、数据库结果或知识检索结果，对输入上下文进行清洗、截断、压缩和重组。与此同时，系统还引入 ContextHub、上下文压缩阈值、历史尾部保留策略和不同模式的上下文上限控制，使模型既能利用足够背景信息，又不至于因上下文过长而降低稳定性。对于办公任务这种连续型交互而言，上下文工程的重要性往往不亚于模型本身。",
                "在企业知识问答方面，项目采用检索增强生成技术，即先通过向量检索找出与问题相关的文档切片，再将检索结果作为证据送入大语言模型。documents_processing.py 显示，系统使用本地嵌入模型 bge-small-zh-v1.5 对文档切片和查询进行向量化，支持根据文档长度自适应调整切片大小与重叠比例，并针对合同类和表格类文档设计了更细粒度的分段策略。相比把整篇文档直接喂给模型，这种检索增强方式能够更好地控制上下文规模，并显著提升回答的针对性与依据性。",
                "检索增强链路中的另一个关键问题是召回结果质量。本项目在文档元数据中保留来源文件名、页码、标题、用户标识等信息，并在查询阶段结合向量相似度、来源过滤与最近文档优先策略组织检索结果。这意味着系统可以在回答问题时更准确地回到具体文件和具体片段，而不是给出脱离材料出处的笼统总结。对于企业办公系统而言，结果是否可溯源直接影响用户信任程度，因此带来源信息的语义检索具有重要工程价值。",
                "除知识库检索外，本项目还实现了自然语言到 SQL 的数据库问答能力。系统不是把数据库查询视为普通文本生成，而是在 database_manager.py 中先定义严格表白名单、表结构摘要、关系映射和 SQL 生成规则，再对模型输出进行只读校验与非法表拦截。查询执行后，系统还会将结构化结果重新组织为用户可读的自然语言解释。由此可见，本项目所实现的数据库智能问答，本质上是一条“模型理解问题-程序约束 SQL-数据库执行结果-模型归纳解释”的复合链路，而非单步文本补全。",
                "此外，模型层能力并不只服务于问答功能，还被复用于报告提纲、邮件草稿、PPT 大纲、审单说明和会议纪要总结等生成场景。不同任务共享统一模型接入层与部分上下文机制，但会根据业务类型采用不同的系统提示词、输入限制和结果组织方式。这种“统一模型底座，多任务差异化封装”的设计可以减少重复开发，同时便于在后期围绕同一模型层继续扩展更多企业办公能力。",
                "综上，本项目的大语言模型技术路线并不是孤立依赖某一家模型服务，而是通过双后端接入、上下文工程、检索增强生成、程序性 SQL 约束和多任务封装形成了一个可治理、可扩展的能力层。该层既保留了大语言模型在语言理解与生成上的优势，又通过文档检索、数据库规则和上下文压缩手段弥补了通用模型在企业场景中的不足，为后续系统设计和功能实现提供了关键技术支柱。",
            ],
        ),
        section(
            "OCR、语音与多模态处理技术",
            [
                "企业办公系统之所以需要多模态技术，是因为真实业务材料从来不只以纯文本形式存在。合同扫描件、票据照片、PDF 报表、截图、装箱单、报关资料、会议录音和口头汇报，都是组织日常运行中常见的信息载体。若系统只能处理键盘输入的文本，便难以覆盖实际工作流程。因此，本项目在文本生成与知识检索之外，还重点建设了 OCR、语音识别与多模态内容接入链路，使更多原始材料能够转化为模型可用的上下文。",
                "在图像与文档识别方面，系统以 PaddleOCR 技术栈为核心，并在 ocr_manager.py 中优先尝试加载 PaddleOCR-VL，若环境或依赖不满足则回退到标准 PaddleOCR 引擎。PaddleOCR-VL 更强调视觉语言联合理解，适合处理复杂版面、文档结构和图文混合内容；标准 PaddleOCR 则提供较稳定的文本检测与识别能力。系统还结合 GPU 可用性自动设置运行设备，并通过动态补充 DLL 路径、关闭部分模型源检查和兼容旧版设备接口等方式解决 Windows 环境下的依赖兼容问题。这说明本项目已经把 OCR 模块视为需要工程打磨的生产能力，而非仅供实验的算法调用。",
                "针对 PDF 与图片文件的异构输入，系统采用分流式处理策略。对于 PDF 文档，先通过 pdf2image 将页面转换为图像，再逐页送入 OCR 引擎；对于普通图片，则直接使用 PIL 读取并转换为 RGB 图像进入识别链路。这样的设计看似基础，实际上解决了企业场景中“同一类材料可能来自扫描件、导出 PDF 或手机拍照”的现实问题，使系统在面对不同来源的文档时仍能维持统一识别接口。与此同时，OCR 模块还能对多页文档执行页面重组、标题重排和表格合并，提高识别结果的可阅读性。",
                "OCR 结果的价值不只在于生成一段可读文本，更在于支持后续结构化抽取、审单比对和问答总结。本项目已经在后端中接入 OCR 结构化解析与记录保存能力，使识别出的字段、文本块和业务信息能够进一步进入规则判断或模型分析链路。例如在审单场景中，OCR 结果可以作为合同、发票、装箱单或报关单之间字段比对的原始依据，从而把“图片识别”转化为“业务核验”的前置步骤。这种设计使 OCR 模块真正融入了业务流程。",
                "在语音处理方面，项目采用百度语音识别服务作为转写底座，并结合本地分片转写机制解决长音频处理问题。voice_manager.py 中实现了基于 pydub 的本地切片转写逻辑，可将会议音频统一转换为符合识别要求的采样格式后按片段送入识别接口。当前工程实现已调整为优先采用本地分片模式，这一路径更适合本地 Supabase 存储与私有化部署环境，也能够避免依赖公网可达音频地址所带来的失败风险。",
                "从任务编排角度看，语音文件处理并不直接绑定在一次同步 HTTP 请求里完成。voice_files_processing.py 负责接收上传音频、写入对象存储、创建任务状态并在后台线程中执行分片转写，最终再将结果交给前端会话页面使用。这样的组织方式能够在不引入额外分布式中间件的前提下，满足会议纪要场景对“先提交、后查看结果”的需求。同时，语音模块与聊天上下文之间存在直接联动，转写文本可以被写入新的会话页面，继续用于总结、追问和任务整理。",
                "多模态处理技术在本项目中的真正价值，在于它不是若干孤立插件的堆砌，而是被整合为统一上下文生产链的一部分。图片和 PDF 经 OCR 后得到可检索、可提问的文本；音频经 ASR 后得到可总结、可追问的会议内容；文档经解析和向量化后进入知识库；这些内容又进一步被写作、问答、审单和报告生成模块复用。换言之，多模态能力真正解决的是“异构材料如何汇聚到同一智能工作流中”的问题。",
                "当然，多模态处理也带来了更高的工程复杂度，例如 OCR 运行环境依赖繁多、GPU 与 CPU 路径差异明显、音频格式与时长差异较大、长文件处理容易引发超时和资源占用问题。本项目通过回退策略、格式转换、分片处理、后台线程和运行时缓存等方式，对这些问题做了务实处理。尽管系统仍有进一步优化空间，但从当前实现看，项目已经初步形成了一套适合企业办公场景的多模态输入处理体系，为后续更深层的文档理解和流程智能化提供了可复用基础。",
            ],
        ),
        section(
            "本章小结",
            [
                "本章围绕系统实现所依赖的核心工具与关键技术进行了系统梳理。可以看到，Enterprise Intelligent Office Agent 2.0 并不是建立在单一模型接口之上的轻量演示程序，而是由前端工作台、后端服务框架、数据持久化平台、大语言模型接入层、检索增强链路和多模态处理模块共同构成的复合型工程系统。React + Vite 保证了统一交互入口的构建效率，FastAPI 保证了多模式能力的接口编排，Supabase 与 PostgreSQL 提供了结构化与非结构化数据底座，Ollama/DeepSeek 与 RAG 技术提供了智能推理和知识增强能力，OCR 与语音模块则拓展了系统对真实办公材料的处理范围。",
                "通过对这些技术基础的分析可以发现，企业智能办公助手的关键不在于“是否接入大模型”，而在于是否建立起一套能够承接真实任务链路的全栈技术体系。只有当交互、数据、模型、规则和多模态输入被组织成可协同、可验证、可扩展的工程结构时，智能办公平台才具备持续落地的价值。基于这一技术基础，下一章将进一步转入系统需求分析，明确本项目面向的业务场景、功能目标、用户角色与非功能约束，为后续总体设计与具体实现提供问题导向上的依据。",
            ],
        ),
    ]

    return {
        "chapter_title": "开发工具及相关技术简介",
        "toc": toc,
        "sections": sections,
    }


def main() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    source_path = repo_root / "artifacts" / "2026届毕业设计说明书.docx"
    output_path = repo_root / "artifacts" / "2026届毕业设计说明书_补全第二章.docx"
    content = make_chapter_content()

    if not source_path.exists():
        raise FileNotFoundError(f"Source docx not found: {source_path}")

    with zipfile.ZipFile(source_path, "r") as zin:
        root = ET.fromstring(zin.read("word/document.xml"))
        body = root.find(qn("body"))
        if body is None:
            raise RuntimeError("word/document.xml missing body")

        paras = get_body_paragraphs(body)
        chapter_title_para = find_paragraph_by_exact_text(paras, "绪论")
        section_title_para = find_paragraph_by_exact_text(paras, "选题背景")
        body_template_para = paras[paras.index(section_title_para) + 1]
        toc_chapter_template_para = next(para for para in paras if paragraph_text(para).startswith("1 绪论"))
        toc_section_template_para = next(para for para in paras if paragraph_text(para).startswith("1.1 "))

        chapter_title_run = chapter_title_para.find(qn("r"))
        section_title_run = section_title_para.find(qn("r"))
        body_template_run = body_template_para.find(qn("r"))
        toc_chapter_run = toc_chapter_template_para.find(qn("r"))
        toc_section_run = toc_section_template_para.find(qn("r"))

        chapter_index = paras.index(chapter_title_para)
        toc_anchor = chapter_title_para
        for idx in range(chapter_index - 1, -1, -1):
            if paragraph_text(paras[idx]).strip():
                break
            toc_anchor = paras[idx]

        toc_lines = list(content["toc"])
        insert_paragraphs_before(
            body,
            toc_anchor,
            toc_chapter_template_para,
            toc_chapter_run,
            toc_lines[:1],
        )
        insert_paragraphs_before(
            body,
            toc_anchor,
            toc_section_template_para,
            toc_section_run,
            toc_lines[1:],
        )

        body_insertions: list[ET.Element] = []
        body_insertions.append(make_page_break_paragraph(body_template_para, body_template_run))

        chapter_para = deepcopy(chapter_title_para)
        set_paragraph_text(chapter_para, str(content["chapter_title"]), chapter_title_run)
        body_insertions.append(chapter_para)

        for item in content["sections"]:
            section_para = deepcopy(section_title_para)
            set_paragraph_text(section_para, str(item["title"]), section_title_run)
            body_insertions.append(section_para)
            for text in item["paragraphs"]:
                para = deepcopy(body_template_para)
                set_paragraph_text(para, text, body_template_run)
                body_insertions.append(para)

        insert_before_sectpr(body, body_insertions)

        output_path.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(output_path, "w") as zout:
            for item in zin.infolist():
                if item.filename != "word/document.xml":
                    zout.writestr(item, zin.read(item.filename))
            zout.writestr(
                "word/document.xml",
                ET.tostring(root, encoding="utf-8", xml_declaration=True),
            )

    print(output_path)


if __name__ == "__main__":
    main()
