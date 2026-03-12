from __future__ import annotations

import importlib.util
from pathlib import Path


def _load_append_module():
    repo_root = Path(__file__).resolve().parents[1]
    module_path = repo_root / "tools" / "append_thesis_ch2.py"
    spec = importlib.util.spec_from_file_location("append_thesis_ch2", module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load module: {module_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> None:
    module = _load_append_module()
    repo_root = Path(__file__).resolve().parents[1]
    template_path = repo_root / "artifacts" / "8_基于大语言模型与多模态协同的企业智能办公助手设计与实现_学号待补充_姓名待补充_软件工程2101班.docx"
    output_path = repo_root / "artifacts" / "2026届毕业设计说明书.docx"
    fallback_output_path = repo_root / "artifacts" / "2026届毕业设计说明书_基于模板补全第二章.docx"

    if not template_path.exists():
        raise FileNotFoundError(f"Template docx not found: {template_path}")

    content = module.make_chapter_content()
    source_path = template_path

    with module.zipfile.ZipFile(source_path, "r") as zin:
        root = module.ET.fromstring(zin.read("word/document.xml"))
        body = root.find(module.qn("body"))
        if body is None:
            raise RuntimeError("word/document.xml missing body")

        paras = module.get_body_paragraphs(body)
        chapter_title_para = module.find_paragraph_by_exact_text(paras, "绪论")
        section_title_para = module.find_paragraph_by_exact_text(paras, "选题背景")
        body_template_para = paras[paras.index(section_title_para) + 1]
        toc_chapter_template_para = next(para for para in paras if module.paragraph_text(para).startswith("1 绪论"))
        toc_section_template_para = next(para for para in paras if module.paragraph_text(para).startswith("1.1 "))

        chapter_title_run = chapter_title_para.find(module.qn("r"))
        section_title_run = section_title_para.find(module.qn("r"))
        body_template_run = body_template_para.find(module.qn("r"))
        toc_chapter_run = toc_chapter_template_para.find(module.qn("r"))
        toc_section_run = toc_section_template_para.find(module.qn("r"))

        chapter_index = paras.index(chapter_title_para)
        toc_anchor = chapter_title_para
        for idx in range(chapter_index - 1, -1, -1):
            if module.paragraph_text(paras[idx]).strip():
                break
            toc_anchor = paras[idx]

        toc_lines = list(content["toc"])
        module.insert_paragraphs_before(
            body,
            toc_anchor,
            toc_chapter_template_para,
            toc_chapter_run,
            toc_lines[:1],
        )
        module.insert_paragraphs_before(
            body,
            toc_anchor,
            toc_section_template_para,
            toc_section_run,
            toc_lines[1:],
        )

        body_insertions: list[module.ET.Element] = []
        body_insertions.append(module.make_page_break_paragraph(body_template_para, body_template_run))

        chapter_para = module.deepcopy(chapter_title_para)
        module.set_paragraph_text(chapter_para, str(content["chapter_title"]), chapter_title_run)
        body_insertions.append(chapter_para)

        for item in content["sections"]:
            section_para = module.deepcopy(section_title_para)
            module.set_paragraph_text(section_para, str(item["title"]), section_title_run)
            body_insertions.append(section_para)
            for text in item["paragraphs"]:
                para = module.deepcopy(body_template_para)
                module.set_paragraph_text(para, text, body_template_run)
                body_insertions.append(para)

        module.insert_before_sectpr(body, body_insertions)

        output_path.parent.mkdir(parents=True, exist_ok=True)
        target_path = output_path
        try:
            with module.zipfile.ZipFile(target_path, "w") as zout:
                for item in zin.infolist():
                    if item.filename != "word/document.xml":
                        zout.writestr(item, zin.read(item.filename))
                zout.writestr(
                    "word/document.xml",
                    module.ET.tostring(root, encoding="utf-8", xml_declaration=True),
                )
        except PermissionError:
            target_path = fallback_output_path
            with module.zipfile.ZipFile(target_path, "w") as zout:
                for item in zin.infolist():
                    if item.filename != "word/document.xml":
                        zout.writestr(item, zin.read(item.filename))
                zout.writestr(
                    "word/document.xml",
                    module.ET.tostring(root, encoding="utf-8", xml_declaration=True),
                )

    print(target_path)


if __name__ == "__main__":
    main()
