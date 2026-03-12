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


def set_paragraph_runs(para: ET.Element, runs: list[tuple[str, ET.Element | None]]) -> None:
    clear_paragraph(para)
    for text, template_run in runs:
        para.append(make_run(text, template_run))


def set_paragraph_text(para: ET.Element, text: str, template_run: ET.Element | None) -> None:
    set_paragraph_runs(para, [(text, template_run)])


def empty_paragraph(para: ET.Element) -> None:
    clear_paragraph(para)


def insert_paragraphs_before(
    body: ET.Element,
    anchor_para: ET.Element,
    template_para: ET.Element,
    template_run: ET.Element | None,
    texts: list[str],
) -> list[ET.Element]:
    inserted: list[ET.Element] = []
    anchor_index = list(body).index(anchor_para)
    for offset, text in enumerate(texts):
        new_para = deepcopy(template_para)
        set_paragraph_text(new_para, text, template_run)
        body.insert(anchor_index + offset, new_para)
        inserted.append(new_para)
    return inserted


def remove_paragraph(body: ET.Element, para: ET.Element) -> None:
    if para in list(body):
        body.remove(para)


def make_content() -> dict:
    return {
        "cover": {
            "year_line": "2026届毕业设计说明书",
            "title": "基于大语言模型与多模态协同的企业智能办公助手设计与实现",
            "college": "计算机科学与工程学院",
            "student": "待补充",
            "supervisor": "待补充",
            "supervisor_title": "待补充",
            "major": "软件工程",
            "class_name": "软件2101",
            "finish_time": "2026-03",
        },
        "cn_abstract": [
            "随着大语言模型、多模态理解与企业数据平台的快速发展，传统办公软件以功能模块孤立、交互入口分散和知识复用效率低为特征的局限愈发明显。尤其在进出口企业、综合型制造企业和服务型组织中，合同、发票、装箱单、报关单、会议录音、制度文档与经营数据往往分散在多个系统与文件载体中，员工需要在聊天、检索、录入、核对、汇总和写作之间频繁切换，导致信息链路断裂、上下文丢失以及决策反馈滞后。基于此，本文围绕企业真实办公场景，设计并实现了一套面向多业务协同的企业智能办公助手系统，以期通过统一交互入口连接文档知识、结构化数据、语音内容、OCR结果与写作任务，提升企业信息处理的整体效率与连续性。",
            "本文以 Enterprise Intelligent Office Agent 2.0 项目为工程基础，构建了以前端 React + Vite、后端 FastAPI 为核心框架的全栈系统架构，并引入 Supabase 作为数据库与对象存储支撑平台，在模型层同时支持本地 Ollama 大模型与云端 DeepSeek 模型切换。系统面向企业办公中的高频任务，集成了多模式对话、RAG 文档检索、自然语言转 SQL、OCR 识别与结构化抽取、会议音频分片转写、报告/PPT/邮件生成、智能审单、管理后台与会话分享等能力，形成了从内容获取、上下文组织到结果生成和留痕管理的完整闭环。",
            "在关键实现机制上，系统设计了统一的模式路由与上下文管理逻辑，使用户能够在同一工作台中完成知识问答、数据查询、会议纪要和审单协同等异构任务；通过文档解析与向量检索策略实现对 PDF、DOCX、TXT 等材料的细粒度切分与语义召回；通过 OCR 与语音识别模块打通图片、扫描件、PDF 与录音文件的内容获取路径；通过历史会话、共享访问、后台审核与规则治理机制增强系统的可追溯性、可维护性与私有化部署适应性。系统的总体设计强调“统一入口、模式协同、结果可验证、工程可扩展”，兼顾交互体验与企业级治理需求。",
            "本文的工程实践说明，面向企业复杂办公流程构建多模态、可扩展、可私有化部署的智能助手，较单一问答系统更能体现现实落地价值。该项目不仅为企业场景下的大语言模型应用提供了一套结构完整的实现范式，也为后续在智能流程编排、知识治理、组织级协同、可信生成与智能体系统集成方面的深入研究奠定了工程基础。",
        ],
        "cn_keywords": "大语言模型；企业智能办公；多模态协同；检索增强生成；OCR；自然语言数据库查询",
        "en_abstract": [
            "With the rapid evolution of large language models, multimodal understanding, and enterprise data platforms, conventional office software is increasingly constrained by isolated function modules, fragmented interaction entrances, and the low efficiency of organizational knowledge reuse. In real business environments, especially in import-export enterprises and comprehensive service organizations, contracts, invoices, packing lists, customs documents, meeting recordings, institutional files, and operational data are usually distributed across different systems and media. Employees have to switch repeatedly among search tools, databases, OCR utilities, communication software, and writing applications, which often causes context interruption, duplicated work, and delayed decision feedback. To address these issues, this thesis designs and implements an enterprise-oriented intelligent office assistant that attempts to connect document knowledge, structured data, audio content, OCR results, and writing tasks through a unified interaction entrance.",
            "The work is based on the practical project Enterprise Intelligent Office Agent 2.0. The system adopts a full-stack architecture with React + Vite on the front end and FastAPI on the back end, while Supabase is used to support data storage and object storage services. At the model layer, the platform supports both locally deployed Ollama models and cloud-based DeepSeek models, so that privacy control and capability enhancement can be balanced in different scenarios. The implemented system integrates multiple enterprise-facing functions, including multimodal chat, retrieval-augmented document question answering, natural-language-to-SQL querying, OCR recognition and structured extraction, chunk-based meeting audio transcription, report and presentation generation, email drafting, intelligent document auditing, management back-office functions, and conversation sharing. As a result, the platform forms a relatively complete closed loop from content acquisition and context organization to result generation and traceable management.",
            "From an engineering perspective, the system highlights unified mode routing, contextual state management, multimodal content acquisition, and verifiable result generation. It demonstrates that an enterprise intelligent assistant should not be reduced to a generic chat box connected to a language model. Instead, it needs to coordinate documents, databases, OCR outputs, audio transcription, business rules, and operational governance in a coherent workflow. The implementation presented in this thesis provides a reusable reference for building privacy-friendly, extensible, and scenario-oriented intelligent office systems, and also offers a practical foundation for future research on trustworthy generation, workflow orchestration, organizational knowledge governance, and enterprise-level agent applications.",
        ],
        "en_keywords": "large language model; enterprise intelligent office; multimodal collaboration; retrieval-augmented generation; OCR; natural language to SQL",
        "toc": [
            "1 绪论 ............................................................ 1",
            "1.1 选题背景 ...................................................... 1",
            "1.2 国内外研究现状 ................................................ 4",
            "1.2.1 国内研究现状 ................................................. 4",
            "1.2.2 国外研究现状 ................................................. 7",
            "1.3 研究内容和意义 ................................................ 10",
            "1.4 本文结构 ...................................................... 13",
        ],
        "chapter_title": "绪论",
        "h11": [
            "近年来，企业数字化建设已经从早期的信息化系统上线，逐步转向以数据驱动、知识驱动和智能驱动为核心的新阶段。与传统 ERP、OA、CRM 更强调流程固化和业务记录不同，新一代智能办公平台开始关注如何借助自然语言交互、语义检索、多模态理解和自动生成能力，将人从大量重复的信息整理与沟通协调工作中解放出来。大语言模型的兴起，使“以对话为入口整合多类工具”的设想第一次具备了大规模工程落地的现实基础，这为企业智能办公系统的发展提供了新的技术拐点。",
            "然而，从企业真实办公流程来看，信息处理从来不是单一的问答任务，而是围绕大量异构材料展开的连续性工作。以进出口和综合贸易型企业为例，业务活动通常伴随合同、报价单、订单、发票、装箱单、提单、报关资料、财务凭证、制度规范、客户邮件、会议录音以及经营统计数据等多种信息对象。这些内容既包含结构化数据，也包含半结构化和非结构化文本，还夹杂扫描件、图片、表格和音频等多种载体。不同信息对象之间存在天然的业务关联，但在现有系统中往往分散于数据库、文件目录、即时通信工具和个人终端之中，给检索、核验、复用和沉淀带来显著成本。",
            "在传统工作模式下，员工往往需要先在知识库或聊天记录中查找背景材料，再到数据库或 BI 系统核对经营数据，然后借助 OCR 工具识别图片或票据，最后将处理结果汇总为邮件、会议纪要、汇报材料或管理建议。这个过程中存在三个突出问题：一是工具切换频繁，信息上下文难以自然延续；二是中间结果依赖人工复制粘贴，重复劳动严重；三是同类问题难以沉淀为可复用的组织知识，导致“问题年年重复、材料次次重找”的低效现象长期存在。对于管理者而言，这种割裂式协同还会进一步削弱业务可视化与追踪能力，使知识资产难以形成稳定积累。",
            "通用大语言模型虽然已经表现出很强的语言理解与生成能力，但若缺乏企业知识库、结构化数据接口、文档解析机制和业务规则约束，其回答很容易停留在“表达流畅但依据不明”的层面。面对企业级任务时，用户真正关心的不只是模型能否回答，更关心答案从何而来、是否能够核验、能否继续追问、能否直接转化为业务结果，以及在敏感场景下是否具备可追溯性。尤其是在审单、财务、合同、制度执行和经营分析等高敏感任务中，可信性、可验证性与可治理性远比单次回答的语言华丽程度更重要。",
            "与此同时，越来越多的企业对数据安全、部署可控性和成本可预测性提出了更高要求。将全部办公数据、会议音频、票据图像和内部制度材料直接交由公共云模型处理，往往会引发保密、合规和长期成本层面的顾虑；而完全依赖传统本地软件，又很难获得大语言模型所提供的自然交互、智能总结和内容生成优势。因此，如何在本地私有化部署、云端能力补充、知识检索增强、多模态输入融合与业务规则约束之间取得平衡，成为当前企业智能办公系统设计中的核心问题。",
            "基于上述背景，构建一套真正服务于企业多场景协同的智能办公助手，不应只是“把聊天框接上大模型”，而应围绕真实任务链路进行系统化设计：前端需要提供统一而清晰的工作台，后端需要具备模式路由、上下文管理与多工具编排能力，底层需要打通文档、数据库、OCR、语音、审单和写作等模块，并形成可复用、可追溯、可扩展的工程体系。只有在这种系统观下，企业智能办公助手才能从演示型应用走向生产型工具。",
            "本文所研究和实现的 Enterprise Intelligent Office Agent 2.0，正是在这一需求背景下展开。项目不以某一单点功能为目标，而是尝试将知识问答、数据库查询、会议纪要、OCR 录入、智能审单、报告与 PPT 生成、邮件起草、共享协作以及管理后台等能力整合到统一平台中，从工程实现层面对企业智能办公系统的体系化设计进行探索。这一工作既具有鲜明的应用导向，也为面向垂直行业场景的智能体系统研究提供了可观测、可分析的实践样本。",
        ],
        "h12_1": [
            "国内关于企业智能办公与智能助手的研究，近年来明显呈现出“大模型能力平台化”和“行业应用场景化”同步推进的趋势。一方面，高校与科研机构围绕中文大模型、知识增强、自然语言交互、智能文档处理和多智能体协同展开了大量探索；另一方面，政企数字化厂商、办公协同平台与云服务提供商也在积极推动生成式人工智能进入知识管理、智能客服、流程自动化、文档审核和经营分析等场景。总体而言，国内研究与产业实践正逐步从“模型能力验证”转向“场景价值验证”。",
            "在知识问答与知识管理方向，国内大量工作聚焦于企业内部知识库的构建与检索增强生成技术的落地。相关研究通常通过向量检索、关键词召回、上下文压缩和引用返回机制，提升模型在制度文件、产品说明、合同模板和业务手册等材料上的回答准确性。这类研究有效缓解了通用模型缺乏企业私域知识的问题，也推动了“知识问答”从开放式聊天转向“带依据回答”的工程形态。但从现有实践看，知识问答模块往往仍作为独立能力存在，与数据查询、文档录入和会议管理等工作链条之间衔接不足。",
            "在文档智能处理方面，国内研究长期重视 OCR、表格识别、版面分析与票据结构化抽取。随着 PaddleOCR 等工具链的成熟，扫描件、票据影像、合同图片和 PDF 文档的识别质量显著提升，文档智能处理从早期单纯的字符识别逐步扩展到字段定位、表单解析、版面恢复和结构化结果导出。对于企业办公场景而言，这类技术极大降低了纸质材料和影像资料进入数字流程的门槛，使发票、合同、报销单和业务凭证等对象能够被进一步纳入智能分析和流程管理之中。",
            "在数据智能与经营分析领域，国内越来越多的研究关注自然语言转 SQL、面向业务人员的数据查询辅助和轻量化经营驾驶舱构建。通过对数据库表结构进行语义压缩、白名单控制、只读策略约束和查询结果再解释，系统能够以较低的交互门槛支持非技术用户直接使用自然语言访问经营数据。这一方向为“人人可查询数据”提供了现实路径，但其难点在于模型生成 SQL 的稳定性、表关系理解能力以及安全边界控制，因此需要数据库规则治理与结果复核机制共同参与。",
            "在语音会议与办公协同方面，国内实践也在不断推进。语音识别、说话内容提炼、会议纪要生成和行动项抽取等技术，正在成为组织协作效率提升的重要支点。相较于传统录音转文字工具，当前研究更加注重转写结果与后续写作、问答和任务追踪之间的联动，希望将会议内容从“记录材料”进一步转化为“可继续利用的上下文资产”。这说明会议音频处理已经不再是孤立的语音任务，而是开始成为企业知识生产链条中的一环。",
            "在业务规则与风险控制方向，国内对智能审单、票据核验、合同条款检查和流程合规辅助的研究热度也持续上升。相关系统通常将 OCR 识别、文本抽取、规则引擎与人工复核结合起来，用于发现单据不一致、字段缺失、金额异常、流程缺项和风险条款等问题。这类研究的价值在于把生成式智能与业务规则治理结合起来，使系统不只会“说”，还能够“查”“核”“拦”，更贴近企业真实生产场景。",
            "尽管国内相关研究与产品发展迅速，但总体上仍存在若干共性不足：其一，许多系统只解决单一场景问题，知识问答、OCR、数据库查询、会议纪要和审单之间缺少统一入口与闭环协同；其二，系统往往更重视模型生成能力，而对结果依据、操作留痕、权限边界和后台治理支持不足；其三，部分方案依赖云端服务较深，在对数据安全和私有部署要求较高的企业中落地阻力较大。上述问题表明，国内企业智能办公系统仍需要在多场景整合、工程化治理和可部署性方面进一步深化研究。",
        ],
        "h12_2": [
            "国外关于智能办公与企业助手的研究起步较早，并在基础模型、软件生态和企业应用三条线上形成了较为成熟的协同格局。特别是在大语言模型能力开放之后，围绕 Copilot、AI Assistant、Agent 和 Retrieval-Augmented Generation 等概念的研究迅速展开。许多国外研究不再把人工智能视为某个独立模块，而是把它作为企业软件的新型交互层，让用户能够以自然语言直接调用文档、数据、流程和协作能力，从而推动工作方式从“菜单驱动”向“语义驱动”转变。",
            "在办公生产力平台层面，以 Microsoft 365 Copilot、Google Workspace 智能助手、Notion AI、Atlassian 智能协作能力等为代表的国外产品，已经较早探索了把邮件、文档、表格、会议、搜索和任务管理纳入同一智能协同界面的路径。这些产品表明，企业用户对智能办公系统的期待并不是获得一个孤立聊天窗口，而是希望在日常使用的软件环境中直接完成摘要、生成、搜索、整理、对比与协同。由此可见，国外研究的一大特点是更强调“能力嵌入业务流程”，而非“能力悬浮于流程之外”。",
            "在模型方法层面，国外关于检索增强生成、工具调用、函数调用、多智能体协同和上下文记忆机制的研究不断成熟。相关工作通过让模型显式访问搜索引擎、知识库、数据库、外部 API 与工作流系统，逐步提高了模型处理复杂任务时的可执行性和可验证性。同时，围绕上下文压缩、长文档理解、会话状态维护与多轮推理链设计的研究，也推动企业助手从单轮应答向任务型协同演进。这为企业场景中的知识问答、流程辅助和综合决策支持提供了方法论基础。",
            "在多模态文档智能方向，国外对文档 AI、版面分析、图文融合理解、表格推理与语音会议协同也有较充分积累。大量研究表明，企业办公资料天然具有多模态特征：一份合同可能同时包含正文、表格和签章，一次会议可能同时涉及语音、字幕、屏幕共享和后续任务列表。因而，企业级智能系统若只具备文本输入能力，将很难覆盖真实工作场景。国外相关研究普遍倾向于把 OCR、ASR、图像理解和文本生成整合到统一框架中，使系统能够围绕一个任务处理多种输入介质。",
            "在会议与协同办公场景中，国外研究还特别强调结果的再利用能力。会议转写不只是得到一段长文本，更重要的是从中抽取决策、行动项、责任人和时间节点，并允许用户继续围绕会议内容追问；文档摘要也不仅是压缩信息量，更要支持引用依据、协作编辑与任务分发。这种“从内容理解走向行动闭环”的思路，为企业智能办公系统的价值定位提供了重要启示。",
            "当然，国外研究与产品也并非没有局限。首先，许多成熟方案建立在高度统一的软件生态和稳定的云服务基础之上，对于中文办公环境、本地私有部署需求和特定行业规则的适配并不天然充分。其次，面向合同审核、单据核验、进出口业务文档协同等具备鲜明本土场景特征的任务，国外通用产品通常缺乏针对性规则体系与行业知识。再次，企业在采用此类系统时还需面对模型调用成本、数据出境、权限治理和组织流程改造等现实问题。",
            "综合来看，国外研究在基础模型方法、Copilot 交互形态、多模态处理与工具协同方面为企业智能办公系统提供了丰富的理论和工程参考，但其成果若要真正服务于中文企业环境，仍需要结合本地部署条件、组织治理模式和行业业务规则进行再设计。也正因为如此，构建一套兼顾企业私域知识、结构化数据、多模态输入、规则治理与前后端一体化体验的智能办公平台，仍然是具有现实研究价值和工程意义的方向。",
        ],
        "h13": [
            "本文的核心目标，是围绕企业真实办公链路，设计并实现一套具备统一入口、多模式协同、多模态理解与可私有化部署特性的智能办公助手系统。与只关注某一功能点的应用不同，本文更强调系统层面的完整性，即把知识问答、数据查询、文档识别、会议转写、写作生成、智能审单和后台治理纳入同一工程框架中，使用户能够在连续上下文下完成多类任务处理。",
            "围绕这一目标，本文首先研究并实现了面向企业智能办公场景的整体技术架构。该架构以前端 React 工作台与后端 FastAPI 服务为基础，结合 Supabase 的数据库与对象存储能力，建立起用户交互层、业务能力层、模型接入层和数据支撑层相互协同的系统结构。通过这种分层设计，系统能够在保持统一交互体验的同时，支持后端各能力模块的独立演进和后续扩展。",
            "其次，本文围绕多模态内容获取与知识增强展开研究。针对企业办公中普遍存在的 PDF、DOCX、TXT、图片、扫描件与音频等资料，系统分别设计了文档解析、向量切分与召回、OCR 识别与结构化抽取、会议音频分片转写等处理机制，使非结构化内容能够进入可检索、可问答、可生成的统一上下文空间。这部分工作解决的并不是“能否接入模型”的问题，而是“企业已有材料如何被模型真正理解和使用”的问题。",
            "再次，本文研究了面向复杂场景的模式路由与交互协同机制。系统根据用户任务目标，将能力分为通用对话、文档检索、数据库查询、会议纪要、OCR 录入、审单和智能写作等模式，并通过上下文组织、历史会话保存、模型后端切换和结果继续追问等策略，实现从单一问答向任务链式处理的过渡。这一设计使系统能够依据任务特征选择不同的数据源、规则链和生成路径，增强了应用层的可用性与准确性。",
            "此外，本文还关注企业级系统不可回避的治理问题，包括历史记录管理、会话分享、后台用户与知识库管理、规则维护、结果留痕与权限边界控制等。对于企业智能办公系统而言，系统是否“可管、可查、可复盘”与是否“会回答”同样重要。因而本文把管理后台、规则配置与任务状态管理纳入系统整体设计之中，以提高系统在长期运行和多人协同环境下的稳定性与可维护性。",
            "从研究意义看，本文的工作在理论与方法层面体现了把大语言模型、检索增强、多模态理解、规则治理和全栈工程实现进行协同整合的尝试。它说明企业级智能系统研究不应局限于模型指标本身，而应关注模型如何嵌入真实组织流程、如何与既有数据系统协同、如何在私域知识约束下生成可验证结果，以及如何在应用层形成可持续演进的技术体系。",
            "从实践价值看，本文所实现的系统面向企业文档处理、经营分析、会议协同、票据识别和审单等高频任务，能够为组织提供一个更统一、更智能、更低切换成本的工作平台。该项目的工程实现为后续企业部署同类系统、扩展智能流程能力、提升知识复用效率和构建私有化智能办公基础设施提供了可直接参考的架构样本与实现路径。",
        ],
        "h14": [
            "为了系统地展开本文的研究内容，全文按照“技术基础—需求分析—系统设计—系统实现—系统验证—总结展望”的逻辑进行组织，使系统研究与工程实践之间形成清晰对应关系。",
            "第一章为绪论，主要介绍课题的研究背景、国内外研究现状、本文的研究内容与研究意义，并对全文结构进行总体说明，从问题提出层面界定本文的研究对象、研究目标与工程价值。",
            "第二章为开发工具及相关技术简介，重点阐述系统实现所依赖的核心技术基础，包括前端 React + Vite 技术栈、后端 FastAPI 框架、Supabase 数据平台、本地与云端大语言模型接入方式、检索增强生成、OCR、语音识别以及相关的工程支撑工具，为后续章节提供必要的技术铺垫。",
            "第三章为系统分析，主要从企业智能办公场景出发，对系统的功能需求、角色需求、业务流程、数据来源与非功能需求进行分析，明确系统需要解决的关键问题以及各功能模块之间的关联关系。",
            "第四章为系统设计，重点说明系统总体架构、前后端分层设计、模式路由机制、上下文管理方式、数据库与存储设计、接口组织方式以及关键模块的交互关系，体现系统从需求到方案的结构化转化过程。",
            "第五章为系统实现，主要围绕多模式对话、文档检索、数据库查询、OCR 录入、会议纪要、审单、智能写作、管理后台与分享能力等核心模块，说明系统在工程层面的具体落地方式，并展示关键实现思路与界面组织形式。",
            "第六章为系统测试，主要从功能正确性、交互稳定性、模块协同性、异常处理能力与部署可用性等角度，对系统进行验证与分析，以检验所设计方案是否满足企业智能办公场景的使用需求。",
            "第七章为总结与展望，对本文完成的主要工作进行归纳，分析当前系统在模型能力、流程联动、性能优化和行业适配方面仍存在的不足，并对后续在智能体协同、流程自动化、知识治理和可信生成方面的拓展方向进行展望。",
        ],
    }


def main() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    template_path = Path(r"C:\Users\LEGION\Downloads\8 课题名称_学号_姓名_软件工程2101班.docx")
    output_dir = repo_root / "artifacts"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "8_基于大语言模型与多模态协同的企业智能办公助手设计与实现_学号待补充_姓名待补充_软件工程2101班.docx"

    content = make_content()

    with zipfile.ZipFile(template_path, "r") as zin:
        xml_bytes = zin.read("word/document.xml")
        root = ET.fromstring(xml_bytes)
        body = root.find(qn("body"))
        if body is None:
            raise RuntimeError("word/document.xml missing body")

        paras = get_body_paragraphs(body)
        if len(paras) < 112:
            raise RuntimeError("Template structure is shorter than expected.")
        original_paras = paras[:]

        # Cover
        empty_paragraph(original_paras[0])   # p1
        set_paragraph_text(original_paras[2], content["cover"]["year_line"], original_paras[2].findall(qn("r"))[1])  # p3
        set_paragraph_text(original_paras[4], content["cover"]["title"], original_paras[4].findall(qn("r"))[1])       # p5
        set_paragraph_runs(
            original_paras[7],
            [
                ("院 、 部：", original_paras[7].findall(qn("r"))[0]),
                (f" {content['cover']['college']} ", original_paras[7].findall(qn("r"))[1]),
            ],
        )
        set_paragraph_runs(
            original_paras[8],
            [
                ("学生姓名：", original_paras[8].findall(qn("r"))[0]),
                (f" {content['cover']['student']} ", original_paras[8].findall(qn("r"))[1]),
            ],
        )
        p10_runs = original_paras[9].findall(qn("r"))
        set_paragraph_runs(
            original_paras[9],
            [
                ("指导教师：", p10_runs[1]),
                (f" {content['cover']['supervisor']} ", p10_runs[3]),
                ("  职称  ", p10_runs[5]),
                (content["cover"]["supervisor_title"], p10_runs[7]),
            ],
        )
        set_paragraph_runs(
            original_paras[10],
            [
                ("专    业：", original_paras[10].findall(qn("r"))[0]),
                (f" {content['cover']['major']} ", original_paras[10].findall(qn("r"))[2]),
            ],
        )
        p12_runs = original_paras[11].findall(qn("r"))
        set_paragraph_runs(
            original_paras[11],
            [
                ("班    级：", p12_runs[0]),
                (f" {content['cover']['class_name']} ", p12_runs[3]),
            ],
        )
        set_paragraph_runs(
            original_paras[12],
            [
                ("完成时间：", original_paras[12].findall(qn("r"))[0]),
                (f" {content['cover']['finish_time']} ", original_paras[12].findall(qn("r"))[1]),
            ],
        )
        for idx in [15, 16, 17]:
            empty_paragraph(original_paras[idx])

        # Chinese abstract
        set_paragraph_text(original_paras[20], "摘  要", original_paras[20].findall(qn("r"))[0])
        body_template_para = original_paras[85]
        body_template_run = original_paras[85].findall(qn("r"))[0]
        for target, text in zip([21, 22, 23, 24], content["cn_abstract"]):
            set_paragraph_text(original_paras[target], text, body_template_run)
        kw_runs = original_paras[25].findall(qn("r"))
        set_paragraph_runs(
            original_paras[25],
            [
                ("关键词", kw_runs[0]),
                ("：", kw_runs[1]),
                (content["cn_keywords"], kw_runs[2]),
            ],
        )
        empty_paragraph(original_paras[28])
        empty_paragraph(original_paras[29])

        # English abstract
        set_paragraph_text(original_paras[39], "ABSTRACT", original_paras[39].findall(qn("r"))[0])
        en_template_run = original_paras[42].findall(qn("r"))[0]
        set_paragraph_text(original_paras[40], content["en_abstract"][0], en_template_run)
        set_paragraph_text(original_paras[41], content["en_abstract"][1], en_template_run)
        insert_paragraphs_before(body, original_paras[42], body_template_para, en_template_run, [content["en_abstract"][2]])
        set_paragraph_text(original_paras[42], f"Key words: {content['en_keywords']}", en_template_run)

        # TOC title and entries
        set_paragraph_text(original_paras[47], "目  录", original_paras[47].findall(qn("r"))[0])
        toc_para_indexes = [48, 49, 50, 51, 52, 53, 54]
        for target, text in zip(toc_para_indexes, content["toc"]):
            toc_para = original_paras[target]
            toc_runs = toc_para.findall(qn("r"))
            template_run = toc_runs[0] if toc_runs else body_template_run
            set_paragraph_text(toc_para, text, template_run)

        # Remove extra TOC lines that belong to later chapters.
        for para in original_paras[55:75]:
            remove_paragraph(body, para)

        # Chapter 1 headings
        set_paragraph_text(original_paras[77], content["chapter_title"], original_paras[77].findall(qn("r"))[0])  # p78
        set_paragraph_text(original_paras[78], "选题背景", original_paras[78].findall(qn("r"))[0])                 # p79

        # 1.1 content: use p80-p83 then insert more before p84.
        for target, text in zip([79, 80, 81, 82], content["h11"][:4]):
            set_paragraph_text(original_paras[target], text, body_template_run)
        insert_paragraphs_before(body, original_paras[83], body_template_para, body_template_run, content["h11"][4:])

        set_paragraph_text(original_paras[83], "国内外研究现状", original_paras[83].findall(qn("r"))[0])           # p84
        set_paragraph_text(original_paras[84], "国内研究现状", original_paras[84].findall(qn("r"))[0])             # p85

        # 1.2.1 content
        domestic_targets = list(range(85, 92))
        for target, text in zip(domestic_targets, content["h12_1"]):
            set_paragraph_text(original_paras[target], text, body_template_run)
        for para in original_paras[92:98]:
            remove_paragraph(body, para)

        set_paragraph_text(original_paras[98], "国外研究现状", original_paras[98].findall(qn("r"))[0])             # p99
        insert_paragraphs_before(body, original_paras[99], body_template_para, body_template_run, content["h12_2"])

        set_paragraph_text(original_paras[99], "研究内容和意义", original_paras[99].findall(qn("r"))[0])           # p100
        insert_paragraphs_before(body, original_paras[100], body_template_para, body_template_run, content["h13"])

        set_paragraph_text(original_paras[100], "本文结构", original_paras[100].findall(qn("r"))[0])                 # p101
        # Replace p102-p107 and insert remaining if needed.
        for target, text in zip(range(101, 107), content["h14"][:6]):
            set_paragraph_text(original_paras[target], text, body_template_run)
        insert_paragraphs_before(body, original_paras[107], body_template_para, body_template_run, content["h14"][6:])

        # Remove all later template paragraphs, keep the body-level sectPr.
        for para in original_paras[107:]:
            remove_paragraph(body, para)

        updated_document = ET.tostring(root, encoding="utf-8", xml_declaration=True)

        with zipfile.ZipFile(output_path, "w") as zout:
            for item in zin.infolist():
                data = updated_document if item.filename == "word/document.xml" else zin.read(item.filename)
                zout.writestr(item, data)

    print(output_path)


if __name__ == "__main__":
    main()
