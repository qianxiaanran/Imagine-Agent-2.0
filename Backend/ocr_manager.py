import os
import sys
import datetime
import io
import pathlib
import tempfile
import threading
from typing import List, Optional

from database_manager import DatabaseManager
from pdf2image import convert_from_bytes
from PIL import Image
import numpy as np
import logging


def _add_torch_dll_paths():
    """
    Windows: 确保 torch 的 DLL 目录在搜索路径中
    """
    try:
        def _prepend_path(p: str):
            if not p:
                return
            paths = os.environ.get("PATH", "").split(";")
            if p not in paths:
                os.environ["PATH"] = ";".join([p] + paths)

        import site
        if not hasattr(os, "add_dll_directory"):
            return
        for sp in site.getsitepackages():
            torch_lib = os.path.join(sp, "torch", "lib")
            if os.path.isdir(torch_lib):
                os.add_dll_directory(torch_lib)
                _prepend_path(torch_lib)
        py_lib_bin = os.path.join(sys.exec_prefix, "Library", "bin")
        if os.path.isdir(py_lib_bin):
            os.add_dll_directory(py_lib_bin)
            _prepend_path(py_lib_bin)
    except Exception:
        pass


def _add_cuda_dll_paths():
    """
    Windows: 确保 Paddle 能找到 nvidia 包的 DLL（cusparse/cudnn 等）
    """
    try:
        def _prepend_path(p: str):
            if not p:
                return
            paths = os.environ.get("PATH", "").split(";")
            if p not in paths:
                os.environ["PATH"] = ";".join([p] + paths)

        import site
        if hasattr(os, "add_dll_directory"):
            for sp in site.getsitepackages():
                nvidia_root = os.path.join(sp, "nvidia")
                if not os.path.isdir(nvidia_root):
                    continue
                for name in (
                    "cuda_runtime",
                    "cublas",
                    "cusparse",
                    "cudnn",
                    "cufft",
                    "curand",
                    "cusolver",
                    "nvjitlink",
                ):
                    bin_dir = os.path.join(nvidia_root, name, "bin")
                    if os.path.isdir(bin_dir):
                        os.add_dll_directory(bin_dir)
                        _prepend_path(bin_dir)
    except Exception:
        # 不阻断主流程
        pass


_add_torch_dll_paths()
_add_cuda_dll_paths()

# 🔧 [Windows 修复] 解决 PaddleOCR 可能出现的 OMP 库冲突错误
os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"
# 关闭 PaddleX 模型源检查，避免联网超时
os.environ["PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK"] = "True"

# 预加载 torch，避免后续由 PaddleX/ModelScope 间接导入时报 DLL 失败
try:
    import torch  # noqa: F401
except Exception as e:
    print(f"[OCR Manager] torch 导入失败，可能导致 OCR 模块不可用: {e}")

import paddle

# 兼容旧版本 Paddle 的 device 接口（PaddleOCR-VL 依赖 paddle.device）
if not hasattr(paddle, "device"):
    class _PaddleDeviceShim:
        @staticmethod
        def set_device(dev: str):
            if hasattr(paddle, "set_device"):
                return paddle.set_device(dev)
            return None

        @staticmethod
        def get_device():
            if hasattr(paddle, "get_device"):
                return paddle.get_device()
            return "cpu"

        @staticmethod
        def is_compiled_with_cuda():
            if hasattr(paddle, "is_compiled_with_cuda"):
                return paddle.is_compiled_with_cuda()
            return False

    paddle.device = _PaddleDeviceShim()

# 引入 PaddleOCR / PaddleOCR-VL
PaddleOCR = None
PaddleOCRVL = None
try:
    from paddleocr import PaddleOCR as _PaddleOCR, PaddleOCRVL as _PaddleOCRVL
    PaddleOCR = _PaddleOCR
    PaddleOCRVL = _PaddleOCRVL
except Exception as e:
    import traceback
    print(f"❌ [OCR Manager] paddleocr 导入失败: {e}")
    traceback.print_exc()
    # 避免重复初始化导致 PDX Reinitialization 报错
    # 若失败则保持 PaddleOCR = None，由上层判断 OCR 是否可用

# 设置日志级别
logging.getLogger("ppocr").setLevel(logging.WARNING)

_OCR_MANAGER_SINGLETON: Optional["OCRManager"] = None
_OCR_MANAGER_LOCK = threading.Lock()


class OCRManager:
    def __init__(self):
        self.db = DatabaseManager()
        self.ocr = None
        self.vl_pipeline = None

        # 0) 设置运行设备（新版本不再接受 use_gpu 参数）
        try:
            use_gpu = False
            if hasattr(paddle, "is_compiled_with_cuda") and paddle.is_compiled_with_cuda():
                use_gpu = True
            if hasattr(paddle, "set_device"):
                paddle.set_device("gpu" if use_gpu else "cpu")
            if use_gpu:
                print("✅ [System] Paddle 设置为 GPU 模式")
            else:
                print("⚠️ [System] Paddle 未检测到 CUDA，OCR 将回退 CPU")
        except Exception as e:
            print(f"⚠️ [System] Paddle 设备设置失败，尝试继续: {e}")

        # 1) 优先初始化 PaddleOCR-VL
        if PaddleOCRVL:
            try:
                print("🚀 [System] 正在加载 PaddleOCR-VL (Visual Language Model)...")
                self.vl_pipeline = PaddleOCRVL(
                    use_doc_orientation_classify=True,
                    use_layout_detection=True,
                )
                print("✅ [System] PaddleOCR-VL 加载成功！将作为首选引擎。")
            except Exception as e:
                error_msg = str(e)
                if "dependency error" in error_msg.lower():
                    print("❌ [System] PaddleOCR-VL 依赖缺失 (通常是 shapely 或 layoutparser 问题)。")
                    print("📌 建议: 运行 `pip install shapely --ignore-installed` 修复。")
                else:
                    print(f"❌ [System] PaddleOCR-VL 加载失败: {e}")
                self.vl_pipeline = None

        # 2) 回退初始化标准 PaddleOCR
        if not PaddleOCR:
            print("❌ [System] PaddleOCR 模块未加载，OCR 功能不可用")
        else:
            print("🚀 [System] 正在加载 PaddleOCR 引擎...")
            try:
                self.ocr = PaddleOCR(
                    ocr_version="PP-OCRv5",
                    use_doc_orientation_classify=False,
                    use_doc_unwarping=False,
                    use_textline_orientation=False,
                    lang='ch'
                )
                print("✅ [System] PaddleOCR 引擎加载完成 (PP-OCRv5)")
            except Exception as e:
                print(f"❌ [System] PaddleOCR 初始化失败: {e}")
                try:
                    # 降级重试
                    self.ocr = PaddleOCR(use_textline_orientation=False, lang='ch')
                    print("✅ [System] PaddleOCR 引擎重试加载完成 (默认版本)")
                except Exception as e2:
                    print(f"❌ [System] 重试依然失败: {e2}")

    def _load_images(self, file_content: bytes, filename: str):
        """
        加载图片或 PDF，返回 PIL Image 列表
        """
        # 1. 处理 PDF
        if filename and filename.lower().endswith(".pdf"):
            try:
                pages = convert_from_bytes(file_content, dpi=300)
                print(f"📄 PDF 解析成功: {filename}, 共 {len(pages)} 页")
                return pages
            except Exception as e:
                error_msg = str(e)
                print(f"⚠️ PDF 解析失败: {error_msg}")
                if "poppler" in error_msg.lower():
                    print("💡 提示: Windows 需要下载 Poppler 并配置环境变量才能解析 PDF")
                return []

        # 2. 处理普通图片
        try:
            img = Image.open(io.BytesIO(file_content)).convert("RGB")
            return [img]
        except Exception as e:
            print(f"❌ 图片加载失败: {e}")
            return []

    def _recognize_with_vl(self, images: List[Image.Image]) -> Optional[str]:
        """
        使用 PaddleOCR-VL 进行识别，输出 Markdown（含表格排版）。
        """
        if not self.vl_pipeline:
            return None

        try:
            print(f"🤖 [PaddleOCR-VL] 开始智能分析 {len(images)} 页文档...")
            input_imgs = [np.array(img) for img in images]

            # 1. 预测
            output = list(self.vl_pipeline.predict(input=input_imgs))

            # 2. 页面重组 (多页合并、表格跨页处理)
            if len(images) > 1:
                try:
                    output = self.vl_pipeline.restructure_pages(
                        output,
                        merge_table=True,
                        relevel_titles=True,
                        merge_pages=True,
                    )
                except TypeError:
                    try:
                        output = self.vl_pipeline.restructure_pages(
                            output,
                            merge_table=True,
                            relevel_titles=True,
                        )
                    except Exception as e_res:
                        print(f"⚠️ [PaddleOCR-VL] 页面重组失败，使用原始结果: {e_res}")
                except Exception as e_res:
                    print(f"⚠️ [PaddleOCR-VL] 页面重组失败，使用原始结果: {e_res}")

            full_markdown = ""

            # 3. 提取 Markdown 内容
            # 为了兼容性，先尝试 save_to_markdown，如果失败则尝试直接读取属性
            with tempfile.TemporaryDirectory() as temp_dir:
                try:
                    for res in output:
                        try:
                            res.save_to_markdown(save_path=temp_dir, pretty=True)
                        except TypeError:
                            res.save_to_markdown(save_path=temp_dir)

                    # 读取生成的 md 文件
                    temp_path = pathlib.Path(temp_dir)
                    md_files = sorted(list(temp_path.glob("*.md")))

                    if md_files:
                        for md_file in md_files:
                            with open(md_file, 'r', encoding='utf-8') as f:
                                full_markdown += f.read() + "\n\n"
                    else:
                        raise FileNotFoundError("No markdown files generated")

                except Exception:
                    # Fallback: 直接从对象属性提取
                    for res in output:
                        if hasattr(res, 'markdown'):
                            md_content = res.markdown
                            if isinstance(md_content, dict):
                                md_texts = md_content.get('markdown_texts')
                                if isinstance(md_texts, list) and md_texts:
                                    full_markdown += "\n\n".join(md_texts) + "\n\n"
                                    continue
                                if 'content' in md_content:
                                    full_markdown += str(md_content['content']) + "\n\n"
                                    continue
                            full_markdown += str(md_content) + "\n\n"

            result_text = full_markdown.strip()
            if not result_text:
                print("⚠️ [PaddleOCR-VL] 识别结果为空")
                return None

            print(f"✅ [PaddleOCR-VL] 识别完成，长度: {len(result_text)}")
            return result_text

        except Exception as e:
            print(f"❌ [PaddleOCR-VL] 运行出错: {e}")
            return None

    def _extract_text_lines(self, result) -> List[str]:
        """
        兼容 PaddleOCR v3+ 多种返回结构，抽取文本行
        """
        lines: List[str] = []
        if not result:
            return lines

        if isinstance(result, dict):
            for key in ("text", "rec_text", "ocr_text"):
                val = result.get(key)
                if isinstance(val, str) and val.strip():
                    lines.append(val.strip())
            for key in ("texts", "rec_texts", "ocr_texts"):
                val = result.get(key)
                if isinstance(val, (list, tuple)):
                    for item in val:
                        if isinstance(item, str) and item.strip():
                            lines.append(item.strip())
            for key in ("data", "result", "results", "ocr_result", "pages"):
                if key in result:
                    lines.extend(self._extract_text_lines(result[key]))
            return lines

        if isinstance(result, (list, tuple)):
            if result and isinstance(result[0], dict):
                for item in result:
                    lines.extend(self._extract_text_lines(item))
                return lines

            # 情况 A: 直接是行列表 [ [box, (text, score)], ... ]
            if result and isinstance(result[0], list) and len(result[0]) >= 2 and isinstance(result[0][1], tuple):
                for line in result:
                    if isinstance(line, list) and len(line) >= 2 and isinstance(line[1], tuple):
                        text_content = line[1][0]
                        if isinstance(text_content, str) and text_content.strip():
                            lines.append(text_content.strip())
                return lines

            # 情况 B: [ [line1, line2, ...] ] (按页包装)
            if result and isinstance(result[0], list) and result[0] and isinstance(result[0][0], list):
                for line in result[0]:
                    if isinstance(line, list) and len(line) >= 2 and isinstance(line[1], tuple):
                        text_content = line[1][0]
                        if isinstance(text_content, str) and text_content.strip():
                            lines.append(text_content.strip())
                if lines:
                    return lines

            # 兜底：递归尝试
            for item in result:
                lines.extend(self._extract_text_lines(item))
            return lines

        return lines

    def _extract_lines_with_boxes(self, result) -> List[dict]:
        """
        从 PaddleOCR 返回结构中抽取文本行 + 位置框
        """
        lines: List[dict] = []
        if not result:
            return lines

        def normalize_box(box):
            try:
                arr = np.array(box)
                if arr.ndim == 1:
                    if arr.size == 4:
                        x1, y1, x2, y2 = arr.tolist()
                        return [[x1, y1], [x2, y1], [x2, y2], [x1, y2]]
                    if arr.size == 8:
                        pts = arr.tolist()
                        return [[pts[0], pts[1]], [pts[2], pts[3]], [pts[4], pts[5]], [pts[6], pts[7]]]
                if arr.ndim == 2 and arr.shape[0] >= 4:
                    return arr[:4].tolist()
            except Exception:
                return None
            return None

        def consume_rec_struct(rec_texts, rec_boxes, rec_scores=None):
            if rec_texts is None or rec_boxes is None:
                return
            for i, text in enumerate(list(rec_texts)):
                if not isinstance(text, str) or not text.strip():
                    continue
                box = rec_boxes[i] if i < len(rec_boxes) else None
                norm = normalize_box(box) if box is not None else None
                score = None
                if rec_scores is not None and i < len(rec_scores):
                    try:
                        score = float(rec_scores[i])
                    except Exception:
                        score = None
                if norm:
                    lines.append({"text": text.strip(), "box": norm, "score": score})

        def walk(item):
            if isinstance(item, list):
                # 形如 [box, (text, score)]
                if len(item) >= 2 and isinstance(item[1], tuple) and len(item[1]) >= 2:
                    box = item[0]
                    text = item[1][0]
                    score = item[1][1]
                    if isinstance(text, str) and text.strip():
                        lines.append({
                            "text": text.strip(),
                            "box": normalize_box(box) or box,
                            "score": float(score) if isinstance(score, (int, float)) else None
                        })
                    return
                for child in item:
                    walk(child)
            elif isinstance(item, dict):
                rec_texts = item.get("rec_texts") if "rec_texts" in item else item.get("texts")
                rec_boxes = item.get("rec_boxes") if "rec_boxes" in item else (
                    item.get("rec_polys") if "rec_polys" in item else item.get("dt_polys")
                )
                rec_scores = item.get("rec_scores") if "rec_scores" in item else item.get("scores")
                if rec_texts is not None and rec_boxes is not None:
                    consume_rec_struct(rec_texts, rec_boxes, rec_scores)
                if "result" in item:
                    walk(item.get("result"))

        walk(result)
        return lines

    def recognize(self, file_obj, filename: str, engine: str = "standard") -> dict:
        """
        执行 OCR 识别
        """
        if not self.ocr and not self.vl_pipeline:
            return {"text": "❌ OCR 引擎未启动", "meta": {}}

        try:
            # 读取二进制内容
            if hasattr(file_obj, "read"):
                if hasattr(file_obj, "seek"):
                    file_obj.seek(0)
                content = file_obj.read()
            else:
                content = file_obj

            # 加载图片
            images = self._load_images(content, filename)

            if not images:
                return {
                    "text": f"❌ 无法解析文件: {filename}\n(如果是 PDF，请检查服务器是否安装了 Poppler)",
                    "meta": {}
                }

            # 用户选择 VL
            if engine == "vl":
                if not self.vl_pipeline:
                    return {
                        "text": "❌ PaddleOCR-VL 未就绪，请检查依赖或改用标准模型。",
                        "meta": {
                            "provider": "PaddleOCR-VL",
                            "pages": len(images),
                            "timestamp": datetime.datetime.now().isoformat()
                        }
                    }
                vl_text = self._recognize_with_vl(images)
                if vl_text:
                    pages = [{"page": idx, "width": int(img.size[0]), "height": int(img.size[1])} for idx, img in enumerate(images)]
                    return {
                        "text": vl_text,
                        "lines": [],
                        "pages": pages,
                        "meta": {
                            "provider": "PaddleOCR-VL",
                            "format": "markdown",
                            "pages": len(images),
                            "timestamp": datetime.datetime.now().isoformat()
                        }
                    }

            all_text = []
            all_lines: List[dict] = []
            pages: List[dict] = []
            print(f"🔍 开始识别: {filename} (共 {len(images)} 页)")

            for page_idx, img in enumerate(images):
                img_np = np.array(img)
                width, height = img.size
                pages.append({
                    "page": page_idx,
                    "width": int(width),
                    "height": int(height)
                })

                # 执行识别
                result = self.ocr.ocr(img_np)
                page_text = self._extract_text_lines(result)
                page_lines = self._extract_lines_with_boxes(result)
                if page_lines:
                    for line in page_lines:
                        line["page"] = page_idx
                    all_lines.extend(page_lines)
                if not page_text:
                    print(f"⚠️ [Standard OCR] 本页未提取到文本: {filename}#page{page_idx}")

                if page_text:
                    all_text.append("\n".join(page_text))

            full_text = "\n\n".join(all_text).strip()
            print(f"✅ 识别完成: {filename}")

            if not full_text:
                # 返回可用占位结果，避免前端判定为空
                fallback_md = (
                    f"# OCR 识别结果（未检测到文本）\n\n"
                    f"- 文件：`{filename}`\n"
                    f"- 可能原因：纯公式/手写/分辨率不足/图片过度压缩\n\n"
                    f"## 建议\n"
                    f"1. 提高分辨率或重新截图\n"
                    f"2. 确保文字清晰、对比度足够\n"
                    f"3. 如为公式截图，建议上传更清晰的原图或 PDF\n\n"
                    f"## 元信息\n\n"
                    f"| 项目 | 值 |\n"
                    f"|---|---|\n"
                    f"| 引擎 | PaddleOCR-Standard |\n"
                    f"| 页数 | {len(images)} |\n"
                    f"| 时间 | {datetime.datetime.now().isoformat()} |\n"
                )
                return {
                    "text": fallback_md,
                    "lines": all_lines,
                    "pages": pages,
                    "meta": {
                        "provider": "PaddleOCR-Standard",
                        "format": "markdown",
                        "pages": len(images),
                        "timestamp": datetime.datetime.now().isoformat()
                    }
                }

            return {
                "text": full_text,
                "lines": all_lines,
                "pages": pages,
                "meta": {
                    "provider": "PaddleOCR-Standard",
                    "pages": len(images),
                    "timestamp": datetime.datetime.now().isoformat()
                }
            }

        except Exception as e:
            print(f"❌ OCR 识别流程异常: {e}")
            import traceback
            traceback.print_exc()
            return {
                "text": f"❌ 识别过程出错: {str(e)}",
                "meta": {}
            }

    def store(self, text: str, source: str) -> str:
        try:
            self.db.insert_document({
                "content": text,
                "source": os.path.basename(source),
                "model": "PaddleOCR-v4",
                "timestamp": datetime.datetime.now().isoformat()
            })
            return "✅ 已保存到数据库"
        except Exception as e:
            return f"❌ 入库失败: {str(e)}"


def get_shared_ocr_manager() -> Optional[OCRManager]:
    global _OCR_MANAGER_SINGLETON
    if _OCR_MANAGER_SINGLETON is not None:
        print("[OCR Manager] Reusing shared OCR instance")
        return _OCR_MANAGER_SINGLETON
    with _OCR_MANAGER_LOCK:
        if _OCR_MANAGER_SINGLETON is None:
            print("[OCR Manager] Creating shared OCR instance")
            _OCR_MANAGER_SINGLETON = OCRManager()
    return _OCR_MANAGER_SINGLETON
