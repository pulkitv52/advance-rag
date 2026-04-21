import base64
import io
import re
from datetime import datetime
from typing import Any, Dict, List, Optional

import markdown
from fpdf import FPDF
from PIL import Image


class ExecutiveReport(FPDF):
    def header(self):
        # Professional Slate/Navy Branding
        self.set_fill_color(30, 41, 59)  # Slate-900
        self.rect(0, 0, 210, 35, "F")

        self.set_font("helvetica", "B", 18)
        self.set_text_color(255, 255, 255)
        self.cell(0, 15, "ENTERPRISE RESEARCH HUB", ln=True, align="L")

        self.set_font("helvetica", "I", 10)
        self.cell(0, 5, "Intelligence Synthesis & Source Evidence Report", ln=True, align="L")
        self.ln(10)

    def footer(self):
        self.set_y(-15)
        self.set_font("helvetica", "I", 8)
        self.set_text_color(128, 128, 128)
        self.cell(
            0,
            10,
            f"Confidential Analysis | Generated on {datetime.now().strftime('%Y-%m-%d %H:%M')} | Page {self.page_no()}",
            align="C",
        )


def sanitize_text(text: str) -> str:
    """Sanitizes text to avoid Latin-1 encoding errors while preserving structure."""
    if not text:
        return ""
    replacements = {
        "\u2013": "-",
        "\u2014": "--",
        "\u2018": "'",
        "\u2019": "'",
        "\u201c": '"',
        "\u201d": '"',
        "\u2022": "*",
        "\u2026": "...",
    }
    for char, replacement in replacements.items():
        text = text.replace(char, replacement)
    return text.encode("latin-1", "replace").decode("latin-1")


def cleanup_html_for_fpdf(html: str) -> str:
    """
    fpdf2's write_html is extremely basic and non-compliant with modern nested HTML.
    This sanitizer flattens the hierarchy to prevent 'Unsupported nested HTML' errors.
    """
    # 1. Map modern tags to fpdf2-compatible ones
    html = html.replace("<em>", "<i>").replace("</em>", "</i>")
    html = html.replace("<strong>", "<b>").replace("</strong>", "</b>")

    # 2. Convert lists to plain text within the context (fpdf2 sometimes chokes on <ul> in <td>)
    # We do this globally first to simplify
    html = re.sub(r"<li>", " * ", html, flags=re.IGNORECASE)
    html = re.sub(r"</li>", "<br/>", html, flags=re.IGNORECASE)
    html = re.sub(r"<(?:ul|ol)[^>]*>", "", html, flags=re.IGNORECASE)
    html = re.sub(r"</(?:ul|ol)>", "", html, flags=re.IGNORECASE)

    # 3. Force table defaults for internal parser
    html = re.sub(
        r"<table", '<table border="1" cellpadding="4" cellspacing="0"', html, flags=re.IGNORECASE
    )

    # 4. Remove structural wrappers that confuse the parser
    html = re.sub(r"<(?:thead|tbody|tfoot)[^>]*>", "", html, flags=re.IGNORECASE)
    html = re.sub(r"</(?:thead|tbody|tfoot)>", "", html, flags=re.IGNORECASE)

    def flatten_cell_content(match):
        tag_open, content, tag_close = match.groups()
        # fpdf2 table cells only support plain text content with no nested HTML.
        clean_content = re.sub(r"<br\s*/?>", " | ", content, flags=re.IGNORECASE)
        clean_content = re.sub(r"<[^>]+>", " ", clean_content)
        clean_content = re.sub(r"\s*\|\s*", " | ", clean_content)
        clean_content = re.sub(r"\s+", " ", clean_content).strip(" |")
        return f"{tag_open}{clean_content}{tag_close}"

    # 5. Target <td> and <th> tags to ensure they are strictly flat
    # We run it twice to handle some simple nesting levels if they exist
    for _ in range(2):
        html = re.sub(
            r"(<(?:td|th)[^>]*>)(.*?)(</(?:td|th)>)",
            flatten_cell_content,
            html,
            flags=re.DOTALL | re.IGNORECASE,
        )

    # 6. Final cleanup: Remove newlines for consistency
    html = html.replace("\n", " ")
    return html


def generate_executive_report(
    query: str, answer: str, sources: List[Dict[str, Any]], visuals: Optional[List[str]] = None
) -> bytes:
    """
    Generates a professional PDF report with Markdown support and embedded visualizations.
    """
    query_clean = sanitize_text(query)

    # 1. Dedicated Markdown Artifact Cleanup
    # Remove raw [Source N](#source-n) markers that might confuse the parser if they escape conversion
    clean_answer = re.sub(r"\[Source \d+\]\(#source-\d+\)", "", answer)

    # 2. Convert Markdown to HTML
    html_answer = markdown.markdown(clean_answer, extensions=["tables", "fenced_code", "nl2br"])

    # 3. Hyper-Sanitize for fpdf2
    html_answer = cleanup_html_for_fpdf(html_answer)
    html_answer = sanitize_text(html_answer)

    pdf = ExecutiveReport()
    pdf.set_auto_page_break(auto=True, margin=20)

    # Configure default HTML styles for 'proper' rendering
    # Heading sizes are increased for Consulting-grade hierarchy
    pdf.add_page()

    # --- SECTION 1: RESEARCH QUERY ---
    pdf.set_font("helvetica", "B", 14)
    pdf.set_text_color(30, 41, 59)
    pdf.cell(0, 10, "1. Research Query", ln=True)
    pdf.set_font("helvetica", "", 11)
    pdf.set_text_color(0, 0, 0)
    pdf.multi_cell(0, 8, query_clean)
    pdf.ln(10)

    # --- SECTION 2: INTELLIGENCE SYNTHESIS ---
    pdf.set_font("helvetica", "B", 14)
    pdf.set_text_color(30, 41, 59)
    pdf.cell(0, 10, "2. Intelligence Synthesis", ln=True)

    # Use write_html for the body content
    # We omit the raw <style> block as fpdf2 handles basic table borders natively when well-formed
    pdf.set_font("helvetica", "", 10)
    pdf.set_text_color(0, 0, 0)
    pdf.write_html(html_answer)
    pdf.ln(10)

    # --- SECTION 3: ANALYTICS & VISUALIZATIONS ---
    if visuals and len(visuals) > 0:
        pdf.add_page()
        pdf.set_font("helvetica", "B", 14)
        pdf.set_text_color(30, 41, 59)
        pdf.cell(0, 10, "3. Visual Intelligence & Ad-Hoc Analytics", ln=True)
        pdf.ln(10)

        for idx, base64_img in enumerate(visuals):
            try:
                # Remove header if present
                if "base64," in base64_img:
                    base64_img = base64_img.split("base64,")[1]

                img_data = base64.b64decode(base64_img)
                img = Image.open(io.BytesIO(img_data))

                # Check for transparency (PNG) and convert to RGB for PDF
                if img.mode in ("RGBA", "LA"):
                    background = Image.new(
                        "RGB", img.size, (250, 252, 254)
                    )  # Matching UI background
                    background.paste(img, mask=img.split()[3])
                    img = background

                img_path = f"/tmp/visual_{idx}.png"
                img.save(img_path)

                # Embed into PDF, maintaining aspect ratio
                current_y = pdf.get_y()
                if current_y > 200:
                    pdf.add_page()
                    current_y = 40

                pdf.image(img_path, x=15, y=current_y, w=180)
                pdf.ln(100)  # Space for image
                pdf.set_font("helvetica", "I", 8)
                pdf.set_text_color(148, 163, 184)
                pdf.cell(
                    0, 10, f"Chart {idx+1}: Business Intelligence Visualization", align="C", ln=True
                )
                pdf.ln(10)
            except Exception as e:
                print(f"Failed to embed visual {idx}: {e}")

    # --- SECTION 4: EVIDENCE APPENDIX ---
    if pdf.get_y() > 200:
        pdf.add_page()
    pdf.set_font("helvetica", "B", 14)
    pdf.set_text_color(30, 41, 59)
    pdf.cell(0, 10, f"{'4' if visuals else '3'}. Verifiable Source Evidence", ln=True)
    pdf.ln(5)

    for i, src in enumerate(sources, 1):
        filename = sanitize_text(src.get("filename", "Unknown"))
        snippet = sanitize_text(src.get("snippet", "No preview available."))

        pdf.set_fill_color(248, 250, 252)
        pdf.set_font("helvetica", "B", 10)
        pdf.cell(0, 8, f"SOURCE [{i}]: {filename}", ln=True, fill=True, border="B")

        pdf.set_font("helvetica", "I", 9)
        page_info = f" (Page {src.get('page')})" if src.get("page") else ""
        pdf.cell(
            0,
            6,
            f"Context Type: Document Grounding {page_info} | Relevance: {src.get('score', 'High')}",
            ln=True,
        )
        pdf.ln(2)
        pdf.set_font("helvetica", "", 9)
        pdf.set_text_color(50, 50, 50)
        pdf.multi_cell(0, 6, snippet)
        pdf.ln(8)
        if pdf.get_y() > 250:
            pdf.add_page()

    pdf_output = pdf.output()
    return bytes(pdf_output) if isinstance(pdf_output, bytearray) else pdf_output
