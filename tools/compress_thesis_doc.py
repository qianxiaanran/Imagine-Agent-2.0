import copy
import io
import shutil
import sys
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path


W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
NS = {"w": W_NS}
W = f"{{{W_NS}}}"

REGISTERED_NAMESPACES = {
    "wpc": "http://schemas.microsoft.com/office/word/2010/wordprocessingCanvas",
    "mc": "http://schemas.openxmlformats.org/markup-compatibility/2006",
    "o": "urn:schemas-microsoft-com:office:office",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    "m": "http://schemas.openxmlformats.org/officeDocument/2006/math",
    "v": "urn:schemas-microsoft-com:vml",
    "wp14": "http://schemas.microsoft.com/office/word/2010/wordprocessingDrawing",
    "wp": "http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing",
    "w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main",
    "w14": "http://schemas.microsoft.com/office/word/2010/wordml",
    "w10": "urn:schemas-microsoft-com:office:word",
    "w15": "http://schemas.microsoft.com/office/word/2012/wordml",
    "wpg": "http://schemas.microsoft.com/office/word/2010/wordprocessingGroup",
    "wpi": "http://schemas.microsoft.com/office/word/2010/wordprocessingInk",
    "wne": "http://schemas.microsoft.com/office/word/2006/wordml",
    "wps": "http://schemas.microsoft.com/office/word/2010/wordprocessingShape",
    "wpsCustomData": "http://www.wps.cn/officeDocument/2013/wpsCustomData",
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    "pic": "http://schemas.openxmlformats.org/drawingml/2006/picture",
}

for prefix, uri in REGISTERED_NAMESPACES.items():
    ET.register_namespace(prefix, uri)


def paragraph_text(p):
    return "".join(t.text or "" for t in p.findall(".//w:t", NS)).strip().replace("\t", " ")


def paragraph_style(p):
    ppr = p.find("w:pPr", NS)
    if ppr is None:
        return ""
    pstyle = ppr.find("w:pStyle", NS)
    if pstyle is None:
        return ""
    return pstyle.get(f"{W}val", "")


def ensure_ppr(p):
    ppr = p.find("w:pPr", NS)
    if ppr is None:
        ppr = ET.Element(f"{W}pPr")
        p.insert(0, ppr)
    return ppr


def set_paragraph_style(p, style_id):
    ppr = ensure_ppr(p)
    pstyle = ppr.find("w:pStyle", NS)
    if pstyle is None:
        pstyle = ET.SubElement(ppr, f"{W}pStyle")
    pstyle.set(f"{W}val", style_id)


def set_paragraph_text(p, text):
    text_nodes = p.findall(".//w:t", NS)
    if text_nodes:
        text_nodes[0].text = text
        for node in text_nodes[1:]:
            node.text = ""
        return

    runs = p.findall("w:r", NS)
    if runs:
        r = runs[0]
    else:
        r = ET.SubElement(p, f"{W}r")
    t = r.find("w:t", NS)
    if t is None:
        t = ET.SubElement(r, f"{W}t")
    t.text = text


def is_heading(block, style_names, levels=("heading 1", "heading 2", "heading 3")):
    if block.tag != f"{W}p":
        return False
    style_id = paragraph_style(block)
    return style_names.get(style_id, "").lower() in levels


def find_paragraph_index(body_items, style_names, text, occurrence=1):
    count = 0
    for idx, item in enumerate(body_items):
        if item.tag != f"{W}p":
            continue
        if paragraph_text(item) == text:
            count += 1
            if count == occurrence:
                return idx
    raise ValueError(f"Paragraph not found: {text}#{occurrence}")


def find_next_paragraph_index(body_items, text, start_idx):
    for idx in range(start_idx + 1, len(body_items)):
        item = body_items[idx]
        if item.tag == f"{W}p" and paragraph_text(item) == text:
            return idx
    raise ValueError(f"Next paragraph not found: {text}")


def delete_range(body_items, start_idx, end_idx):
    del body_items[start_idx:end_idx]


def delete_heading_only(body_items, style_names, text, occurrence=1):
    idx = find_paragraph_index(body_items, style_names, text, occurrence)
    del body_items[idx]


def delete_section(body_items, style_names, start_text, next_text, start_occurrence=1):
    start_idx = find_paragraph_index(body_items, style_names, start_text, start_occurrence)
    next_idx = find_next_paragraph_index(body_items, next_text, start_idx)
    delete_range(body_items, start_idx, next_idx)


def delete_section_after_anchor(body_items, style_names, anchor_text, start_text, next_text):
    anchor_idx = find_paragraph_index(body_items, style_names, anchor_text)
    start_idx = find_next_paragraph_index(body_items, start_text, anchor_idx)
    next_idx = find_next_paragraph_index(body_items, next_text, start_idx)
    delete_range(body_items, start_idx, next_idx)


def rename_paragraph(body_items, style_names, old_text, new_text, occurrence=1, style_id=None):
    idx = find_paragraph_index(body_items, style_names, old_text, occurrence)
    p = body_items[idx]
    set_paragraph_text(p, new_text)
    if style_id:
        set_paragraph_style(p, style_id)


def move_section_before(body_items, style_names, start_text, next_text, before_text):
    start_idx = find_paragraph_index(body_items, style_names, start_text)
    next_idx = find_next_paragraph_index(body_items, next_text, start_idx)
    chunk = body_items[start_idx:next_idx]
    del body_items[start_idx:next_idx]
    before_idx = find_paragraph_index(body_items, style_names, before_text)
    body_items[before_idx:before_idx] = chunk


def trim_section_text(body_items, style_names, heading_text, keep_paragraphs):
    heading_idx = find_paragraph_index(body_items, style_names, heading_text)
    next_heading_idx = len(body_items)
    for idx in range(heading_idx + 1, len(body_items)):
        if is_heading(body_items[idx], style_names):
            next_heading_idx = idx
            break

    kept = 0
    delete_idx = []
    for idx in range(heading_idx + 1, next_heading_idx):
        item = body_items[idx]
        if item.tag != f"{W}p":
            continue
        if item.findall(".//w:drawing", NS):
            continue
        text = paragraph_text(item)
        if not text:
            continue
        kept += 1
        if kept > keep_paragraphs:
            delete_idx.append(idx)

    for idx in reversed(delete_idx):
        del body_items[idx]


def get_style_maps(styles_root):
    style_id_to_name = {}
    style_name_to_id = {}
    for style in styles_root.findall("w:style", NS):
        style_id = style.get(f"{W}styleId", "")
        name_el = style.find("w:name", NS)
        if not style_id or name_el is None:
            continue
        name = name_el.get(f"{W}val", "")
        style_id_to_name[style_id] = name
        style_name_to_id[name.lower()] = style_id
    return style_id_to_name, style_name_to_id


def main():
    if len(sys.argv) != 3:
        raise SystemExit("usage: compress_thesis_doc.py SOURCE TARGET")

    source = Path(sys.argv[1])
    target = Path(sys.argv[2])
    if not source.exists():
        raise SystemExit(f"source not found: {source}")

    target.parent.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(source, "r") as zin:
        files = {name: zin.read(name) for name in zin.namelist()}

    styles_root = ET.fromstring(files["word/styles.xml"])
    style_names, style_ids = get_style_maps(styles_root)
    h2 = style_ids["heading 2"]

    doc_root = ET.fromstring(files["word/document.xml"])
    doc_root.set(f"{{{REGISTERED_NAMESPACES['mc']}}}Ignorable", "w14")
    body = doc_root.find("w:body", NS)
    body_items = list(body)

    rename_paragraph(body_items, style_names, "系统开发环境与工具选择", "开发环境与工具")
    rename_paragraph(body_items, style_names, "前端界面构建与交互实现技术", "前端开发技术")
    rename_paragraph(body_items, style_names, "后端服务框架与接口组织技术", "后端开发技术")
    rename_paragraph(body_items, style_names, "数据持久化、对象存储与会话管理技术", "数据存储与数据库技术")
    rename_paragraph(body_items, style_names, "OCR、语音与多模态处理技术", "OCR与语音识别技术")

    delete_section(body_items, style_names, "场景问题与建设目标分析", "可行性分析")
    rename_paragraph(body_items, style_names, "技术可行性分析", "技术可行性")
    rename_paragraph(body_items, style_names, "经济可行性分析", "经济可行性")
    rename_paragraph(body_items, style_names, "运行可行性分析", "运行可行性")
    rename_paragraph(body_items, style_names, "用户角色与业务场景分析", "系统需求分析")
    delete_section(body_items, style_names, "核心业务场景分析", "功能需求分析")
    delete_heading_only(body_items, style_names, "功能需求分析")
    rename_paragraph(body_items, style_names, "智能对话与知识服务需求", "功能需求分析")
    delete_heading_only(body_items, style_names, "数据查询与经营分析需求")
    delete_heading_only(body_items, style_names, "OCR、文档解析与会议纪要需求")
    delete_heading_only(body_items, style_names, "智能审单与内容生成需求")
    delete_heading_only(body_items, style_names, "管理后台与共享协同需求")
    rename_paragraph(body_items, style_names, "业务流程与数据流程分析", "业务流程分析")
    rename_paragraph(body_items, style_names, "文档知识处理流程分析", "智能对话与知识问答流程")
    rename_paragraph(body_items, style_names, "会议音频处理流程分析", "数据决策与内容生成流程")
    rename_paragraph(body_items, style_names, "数据问答与审单处理流程分析", "智能审单与风险处理流程")
    delete_heading_only(body_items, style_names, "非功能需求分析")
    rename_paragraph(body_items, style_names, "性能需求", "非功能需求分析")
    delete_heading_only(body_items, style_names, "安全需求")
    delete_heading_only(body_items, style_names, "可维护性与可扩展性需求")
    delete_heading_only(body_items, style_names, "易用性与部署适应性需求")

    delete_section(body_items, style_names, "设计目标与原则", "系统总体架构设计")
    delete_section(body_items, style_names, "前端系统设计", "后端系统设计")
    move_section_before(body_items, style_names, "数据与存储设计", "关键模块设计", "后端系统设计")
    delete_section(body_items, style_names, "接口与安全机制设计", "本章小结")
    rename_paragraph(body_items, style_names, "系统总体架构设计", "总体设计")
    rename_paragraph(body_items, style_names, "分层总体架构设计", "系统总体架构设计")
    rename_paragraph(body_items, style_names, "功能模块架构设计", "功能模块划分设计")
    delete_section(body_items, style_names, "部署与运行架构设计", "数据与存储设计")
    rename_paragraph(body_items, style_names, "数据与存储设计", "数据库设计")
    rename_paragraph(body_items, style_names, "业务数据库与角色权限数据设计", "数据库逻辑结构设计")
    rename_paragraph(body_items, style_names, "会话历史、分享与知识库数据设计", "主要数据表设计")
    delete_section(body_items, style_names, "对象存储与运行时文件设计", "后端系统设计")
    rename_paragraph(body_items, style_names, "后端系统设计", "核心模块设计")
    delete_section(body_items, style_names, "路由装配与接口分层设计", "模式路由与上下文管理设计")
    rename_paragraph(body_items, style_names, "模式路由与上下文管理设计", "对话与上下文管理模块设计")
    delete_section(body_items, style_names, "异步任务与后台处理设计", "关键模块设计")
    rename_paragraph(body_items, style_names, "关键模块设计", "特色业务模块设计")
    rename_paragraph(body_items, style_names, "文档检索增强问答模块设计", "文档检索与知识库模块设计")
    rename_paragraph(body_items, style_names, "OCR 与会议纪要模块设计", "OCR与语音处理模块设计")
    rename_paragraph(body_items, style_names, "审单、报告与 PPT 生成模块设计", "智能审单模块设计")
    rename_paragraph(body_items, style_names, "数据库智能问答模块设计", "决策分析与智能写作模块设计")

    rename_paragraph(body_items, style_names, "系统实现概述", "系统总体功能介绍")
    delete_heading_only(body_items, style_names, "前端核心功能实现")
    delete_heading_only(body_items, style_names, "后端核心服务实现")
    delete_heading_only(body_items, style_names, "智能能力模块实现")
    delete_section(body_items, style_names, "登录认证与用户会话实现", "统一工作台与多模式交互实现")
    rename_paragraph(body_items, style_names, "统一工作台与多模式交互实现", "智能对话与知识问答模块实现", style_id=h2)
    delete_section(body_items, style_names, "文件上传、OCR 与会议纪要前端实现", "写作中心、分享与后台界面实现")
    delete_section(body_items, style_names, "写作中心、分享与后台界面实现", "应用启动、路由装配与中间件实现")
    delete_section(body_items, style_names, "应用启动、路由装配与中间件实现", "聊天服务与上下文编排实现")
    delete_heading_only(body_items, style_names, "聊天服务与上下文编排实现")
    delete_heading_only(body_items, style_names, "历史会话、分享与认证接口实现")
    delete_section(body_items, style_names, "文档解析与检索增强问答实现", "数据库智能问答实现")
    delete_section(body_items, style_names, "数据库智能问答实现", "OCR 与会议音频处理实现")
    rename_paragraph(body_items, style_names, "OCR 与会议音频处理实现", "OCR识别、语音处理与智能审单模块实现", style_id=h2)
    delete_heading_only(body_items, style_names, "智能审单流程实现")
    rename_paragraph(body_items, style_names, "报告、邮件与 PPT 生成实现", "数据决策与智能创作模块实现", style_id=h2)
    rename_paragraph(body_items, style_names, "管理与运行支撑实现", "用户权限与系统管理模块实现")
    delete_heading_only(body_items, style_names, "角色治理与后台管理实现")
    delete_heading_only(body_items, style_names, "运行时资源、安全机制与可维护性实现")

    rename_paragraph(body_items, style_names, "系统测试与分析", "系统测试")
    rename_paragraph(body_items, style_names, "测试目标与测试环境", "测试环境与测试方法")
    delete_heading_only(body_items, style_names, "测试目标")
    delete_heading_only(body_items, style_names, "测试环境")
    delete_heading_only(body_items, style_names, "测试方法与评价指标")
    delete_heading_only(body_items, style_names, "登录认证与会话管理功能测试")
    delete_heading_only(body_items, style_names, "智能对话、知识库与数据库问答功能测试")
    delete_heading_only(body_items, style_names, "OCR 与会议纪要功能测试")
    delete_heading_only(body_items, style_names, "审单、写作与 PPT 生成功能测试")
    delete_heading_only(body_items, style_names, "分享协同与后台管理功能测试")
    rename_paragraph(body_items, style_names, "非功能测试", "性能测试")
    delete_heading_only(body_items, style_names, "性能与响应测试")
    delete_heading_only(body_items, style_names, "安全与权限控制测试")
    delete_heading_only(body_items, style_names, "稳定性与异常恢复测试")
    delete_heading_only(body_items, style_names, "兼容性与易用性测试")
    rename_paragraph(body_items, style_names, "测试结果分析与效果验证", "测试结果分析")
    delete_heading_only(body_items, style_names, "测试结果综合分析")
    delete_heading_only(body_items, style_names, "系统应用价值验证")
    delete_heading_only(body_items, style_names, "存在的问题与改进方向")

    rename_paragraph(body_items, style_names, "全文工作总结", "总结")
    delete_heading_only(body_items, style_names, "研究背景与目标回顾")
    delete_heading_only(body_items, style_names, "主要研究内容与实现成果总结")
    delete_heading_only(body_items, style_names, "创新点与应用价值总结")
    delete_section(body_items, style_names, "系统不足与研究局限", "未来工作展望")
    rename_paragraph(body_items, style_names, "未来工作展望", "展望")
    delete_heading_only(body_items, style_names, "智能能力与多模态协同的演进方向")
    delete_heading_only(body_items, style_names, "企业级平台化与治理能力的演进方向")
    delete_heading_only(body_items, style_names, "面向研究与应用结合的拓展方向")
    delete_section_after_anchor(body_items, style_names, "展望", "本章小结", "参考文献")

    trim_section_text(body_items, style_names, "研究内容和意义", 4)
    trim_section_text(body_items, style_names, "本文结构", 2)
    trim_section_text(body_items, style_names, "总结", 6)
    trim_section_text(body_items, style_names, "展望", 5)

    body[:] = body_items
    files["word/document.xml"] = ET.tostring(doc_root, encoding="utf-8", xml_declaration=True)

    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED) as zout:
        for name, payload in files.items():
            zout.writestr(name, payload)


if __name__ == "__main__":
    main()
