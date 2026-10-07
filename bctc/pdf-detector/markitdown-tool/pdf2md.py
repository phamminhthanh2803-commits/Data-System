#!/usr/bin/env python3
"""
Batch convert PDF -> Markdown: Microsoft markitdown + OCR Tesseract (song song theo trang).

Cách dùng:
    python pdf2md.py <duong_dan> [<duong_dan> ...] [tuy_chon]

<duong_dan>: 1 file .pdf, 1 thư mục, hoặc nhiều cái cùng lúc.

Tùy chọn:
    -o, --out DIR     Thư mục xuất .md (mặc định: cùng chỗ file PDF)
    -r, --recursive   Quét cả thư mục con
    -f, --force       Ghi đè file .md đã tồn tại (mặc định: bỏ qua)
    -j, --jobs N      Số trang OCR song song (mặc định: ~3/4 số luồng CPU)
    --ocr MODE        off | auto | force  (mặc định: auto)
    -l, --lang LANG   Ngôn ngữ OCR (mặc định: vie+eng)
    --dpi N           DPI render trang khi OCR (mặc định: 300). Hạ xuống 250 = nhanh hơn.
    --psm N           Tesseract page segmentation mode (mặc định: 6)
    --layout {on,off} Dựng lại bảng theo toạ độ chữ, bọc code-block (mặc định: on)

Mẹo tốc độ (khối lượng lớn):
    - jobs để mặc định (đã bằng ~3/4 số luồng CPU) là tối ưu cho đa số máy.
    - --dpi 250 nhanh hơn ~30% so với 300, chữ to vẫn đọc tốt; bảng chữ nhỏ thì giữ 300+.
    - --layout off + --ocr force nhanh hơn chút nếu không cần giữ cột bảng.

Ví dụ:
    python pdf2md.py "D:\\Tai lieu" -r                  # auto-OCR + giữ bảng, song song trang
    python pdf2md.py "D:\\Scan" -r --dpi 250            # ưu tiên tốc độ
    python pdf2md.py "D:\\Tai lieu" -r --ocr off        # PDF có sẵn text, bỏ OCR
"""
import argparse
import os
import statistics
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

# Tắt đa luồng nội bộ của Tesseract/OpenMP: ta tự song song ở mức trang -> tránh tranh CPU.
# Phải set TRƯỚC khi gọi tesseract.
os.environ.setdefault("OMP_THREAD_LIMIT", "1")
os.environ.setdefault("OMP_NUM_THREADS", "1")

# Ép console Windows in được tiếng Việt (tránh lỗi cp1252)
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:  # noqa: BLE001
    pass

SCRIPT_DIR = Path(__file__).resolve().parent

_TESS_EXE_CANDIDATES = [
    r"C:\Program Files\Tesseract-OCR\tesseract.exe",
    r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
    str(Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Tesseract-OCR" / "tesseract.exe"),
]
_BUNDLED_TESSDATA = SCRIPT_DIR / "tessdata"

TEXT_THRESHOLD = 40  # dưới ngưỡng ký tự này coi như trang ảnh -> OCR


def _setup_ocr():
    try:
        import pytesseract  # noqa: F401
        import pypdfium2  # noqa: F401
    except ImportError as e:
        return f"thiếu thư viện OCR ({e}). Chạy: pip install pytesseract pypdfium2"

    import pytesseract as pt

    exe = next((p for p in _TESS_EXE_CANDIDATES if p and Path(p).exists()), None)
    if exe:
        pt.pytesseract.tesseract_cmd = exe
    if _BUNDLED_TESSDATA.exists():
        os.environ["TESSDATA_PREFIX"] = str(_BUNDLED_TESSDATA)
    return None


def collect_pdfs(paths, recursive):
    pdfs = []
    for p in paths:
        path = Path(p)
        if not path.exists():
            print(f"  [bỏ qua] không tồn tại: {path}")
            continue
        if path.is_file():
            if path.suffix.lower() == ".pdf":
                pdfs.append(path)
            else:
                print(f"  [bỏ qua] không phải PDF: {path}")
        elif path.is_dir():
            pattern = "**/*.pdf" if recursive else "*.pdf"
            pdfs.extend(sorted(path.glob(pattern)))
    seen, unique = set(), []
    for f in pdfs:
        key = f.resolve()
        if key not in seen:
            seen.add(key)
            unique.append(f)
    return unique


def ocr_layout(img, lang, psm):
    """OCR giữ bố cục: căn cột theo toạ độ x của chữ (số trong bảng thẳng hàng)."""
    import pytesseract as pt
    from pytesseract import Output

    config = f"--psm {psm} -c preserve_interword_spaces=1"
    data = pt.image_to_data(img, lang=lang, config=config, output_type=Output.DICT)
    n = len(data["text"])

    char_w = []
    for i in range(n):
        w = data["text"][i]
        if w and w.strip() and data["width"][i] > 0:
            char_w.append(data["width"][i] / max(1, len(w)))
    cw = statistics.median(char_w) if char_w else 10.0

    lines = {}
    for i in range(n):
        word = data["text"][i]
        if not word or not word.strip():
            continue
        key = (data["block_num"][i], data["par_num"][i], data["line_num"][i])
        lines.setdefault(key, []).append((data["left"][i], word))

    out = []
    for key in sorted(lines.keys()):
        words = sorted(lines[key], key=lambda t: t[0])
        line_str = ""
        for left, word in words:
            col = int(round(left / cw))
            if col < len(line_str) + 1:
                col = len(line_str) + (1 if line_str else 0)
            if col > len(line_str):
                line_str += " " * (col - len(line_str))
            line_str += word
        out.append(line_str.rstrip())
    while out and not out[0].strip():
        out.pop(0)
    while out and not out[-1].strip():
        out.pop()
    return "\n".join(out)


def ocr_page(img, lang, psm, layout):
    import pytesseract as pt
    if layout:
        return f"```text\n{ocr_layout(img, lang, psm)}\n```"
    return pt.image_to_string(img, lang=lang).strip()


class OcrEngine:
    """Pool OCR dùng chung cho toàn bộ job, có semaphore chặn tràn RAM."""

    def __init__(self, workers, lang, psm, layout):
        self.pool = ThreadPoolExecutor(max_workers=workers)
        self.sem = threading.Semaphore(workers * 2)
        self.lang, self.psm, self.layout = lang, psm, layout

    def submit(self, img):
        self.sem.acquire()

        def run():
            try:
                return ocr_page(img, self.lang, self.psm, self.layout)
            finally:
                self.sem.release()

        return self.pool.submit(run)

    def shutdown(self):
        self.pool.shutdown(wait=True)


def process_file_ocr(pdf_path, out_dir, mode, dpi, engine):
    """Render trang tuần tự, đẩy OCR vào pool dùng chung (song song theo trang)."""
    import pypdfium2 as pdfium

    if out_dir is not None:
        target = Path(out_dir) / (pdf_path.stem + ".md")
    else:
        target = pdf_path.with_suffix(".md")

    scale = dpi / 72.0
    slots = []  # ('text', str) | ('ocr', future)
    pdf = pdfium.PdfDocument(str(pdf_path))
    try:
        n = len(pdf)
        for i in range(n):
            page = pdf[i]
            page_text = ""
            if mode != "force":
                tp = page.get_textpage()
                page_text = tp.get_text_range() or ""
                tp.close()
            if mode == "force" or len(page_text.strip()) < TEXT_THRESHOLD:
                img = page.render(scale=scale).to_pil()
                slots.append(("ocr", engine.submit(img)))
            else:
                slots.append(("text", page_text.strip()))
            page.close()
    finally:
        pdf.close()

    parts = []
    for i, (kind, val) in enumerate(slots):
        if kind == "ocr":
            body = val.result()
            parts.append(f"<!-- trang {i + 1} (OCR) -->\n{body}")
        else:
            parts.append(f"<!-- trang {i + 1} (text) -->\n{val}")

    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("\n\n".join(parts), encoding="utf-8")
    return str(target)


def process_file_markitdown(pdf_path, out_dir, md_obj):
    if out_dir is not None:
        target = Path(out_dir) / (pdf_path.stem + ".md")
    else:
        target = pdf_path.with_suffix(".md")
    text = md_obj.convert(str(pdf_path)).text_content
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")
    return str(target)


def main():
    cpu = os.cpu_count() or 4
    default_jobs = max(2, (cpu * 3) // 4)

    parser = argparse.ArgumentParser(
        description="Batch PDF -> Markdown (markitdown + OCR Tesseract, song song theo trang)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("paths", nargs="+", help="File .pdf hoặc thư mục")
    parser.add_argument("-o", "--out", default=None, help="Thư mục xuất .md")
    parser.add_argument("-r", "--recursive", action="store_true", help="Quét thư mục con")
    parser.add_argument("-f", "--force", action="store_true", help="Ghi đè file .md đã có")
    parser.add_argument("-j", "--jobs", type=int, default=default_jobs,
                        help=f"Số trang OCR song song (mặc định: {default_jobs})")
    parser.add_argument("--ocr", choices=["off", "auto", "force"], default="auto",
                        help="Chế độ OCR (mặc định: auto)")
    parser.add_argument("-l", "--lang", default="vie+eng", help="Ngôn ngữ OCR")
    parser.add_argument("--dpi", type=int, default=300, help="DPI render trang khi OCR")
    parser.add_argument("--psm", type=int, default=6, help="Tesseract PSM (mặc định 6)")
    parser.add_argument("--layout", choices=["on", "off"], default="on",
                        help="Dựng bảng theo toạ độ + bọc code-block (mặc định: on)")
    args = parser.parse_args()

    pdfs = collect_pdfs(args.paths, args.recursive)
    if not pdfs:
        print("Không tìm thấy file PDF nào.")
        return

    # lọc sẵn file đã có .md (nếu không --force)
    todo = []
    skip = 0
    for pdf in pdfs:
        target = (Path(args.out) / (pdf.stem + ".md")) if args.out else pdf.with_suffix(".md")
        if target.exists() and not args.force:
            skip += 1
        else:
            todo.append(pdf)

    jobs = max(1, args.jobs)
    layout = args.layout == "on"

    print(f"PDF: {len(pdfs)} (làm {len(todo)}, bỏ qua {skip}) | OCR={args.ocr} "
          f"| lang={args.lang} | dpi={args.dpi} | psm={args.psm} | layout={args.layout} "
          f"| jobs={jobs} | CPU={cpu}\n")
    if not todo:
        print("Không còn file nào cần làm.")
        return

    ok = err_cnt = 0
    done = 0
    total = len(todo)
    t0 = time.time()

    if args.ocr == "off":
        try:
            from markitdown import MarkItDown
        except ImportError:
            print('Chưa cài markitdown. Chạy: pip install "markitdown[pdf]"')
            sys.exit(1)
        md_obj = MarkItDown()
        with ThreadPoolExecutor(max_workers=jobs) as pool:
            futs = {pool.submit(process_file_markitdown, p, args.out, md_obj): p for p in todo}
            for fut in as_completed(futs):
                pdf = futs[fut]
                done += 1
                try:
                    fut.result()
                    ok += 1
                    print(f"[{done}/{total}] OK    {pdf.name}")
                except Exception as e:  # noqa: BLE001
                    err_cnt += 1
                    print(f"[{done}/{total}] LỖI   {pdf.name} -> {e}")
    else:
        err = _setup_ocr()
        if err:
            print(f"Không bật được OCR: {err}")
            sys.exit(1)
        engine = OcrEngine(jobs, args.lang, args.psm, layout)
        # vài luồng đọc/render file song song để luôn có việc đẩy vào pool OCR
        file_workers = max(2, jobs // 3)
        try:
            with ThreadPoolExecutor(max_workers=file_workers) as fpool:
                futs = {
                    fpool.submit(process_file_ocr, p, args.out, args.ocr, args.dpi, engine): p
                    for p in todo
                }
                for fut in as_completed(futs):
                    pdf = futs[fut]
                    done += 1
                    try:
                        fut.result()
                        ok += 1
                        print(f"[{done}/{total}] OK    {pdf.name}")
                    except Exception as e:  # noqa: BLE001
                        err_cnt += 1
                        print(f"[{done}/{total}] LỖI   {pdf.name} -> {e}")
        finally:
            engine.shutdown()

    dt = time.time() - t0
    print(f"\nXong trong {dt:.1f}s | OK: {ok} | Bỏ qua: {skip} | Lỗi: {err_cnt}")


if __name__ == "__main__":
    main()
