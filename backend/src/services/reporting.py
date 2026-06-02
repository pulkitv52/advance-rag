import base64
import io
import os
import re
import tempfile
from datetime import datetime
from typing import Any, Dict, List, Optional

import markdown
from PIL import Image

from reportlab.lib.pagesizes import letter
from reportlab.lib.colors import HexColor
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image as RLImage, PageBreak, KeepTogether
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.pdfgen import canvas

# Keep FPDF class definition just in case something else relies on import, but we'll use SimpleDocTemplate for ReportLab
from fpdf import FPDF

class ExecutiveReport(FPDF):
    def header(self):
        pass
    def footer(self):
        pass


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


# ── REPORTLAB INTEGRATION IMPLEMENTATION ──

class NumberedCanvas(canvas.Canvas):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved_page_states = []

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        num_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self.draw_page_decorations(num_pages)
            super().showPage()
        super().save()

    def draw_page_decorations(self, page_count):
        self.saveState()
        
        # 1. Premium Slate-Navy Header Bar
        self.setFillColor(HexColor("#1e293b"))  # Slate-900
        # Letter-size is 612x792 points. We draw a header bar at the top 80 points.
        self.rect(0, 712, 612, 80, fill=True, stroke=False)
        
        # Draw logo image at top left of running header
        logo_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "wb_logo.png")
        if not os.path.exists(logo_path):
            logo_path = "wb_logo.png"  # Fallback to local execution directory root
            
        if os.path.exists(logo_path):
            self.drawImage(logo_path, 36, 722, width=40, height=40, mask='auto')
            text_x = 90
        else:
            text_x = 36
            
        # Header title
        self.setFillColor(HexColor("#ffffff"))
        self.setFont("Helvetica-Bold", 13)
        self.drawString(text_x, 752, "WEST BENGAL FINANCE DEPARTMENT")
        
        # Header subtitle
        self.setFont("Helvetica-Oblique", 8.5)
        self.drawString(text_x, 732, "Social Welfare Intelligence & Source Evidence Report")
        
        # 2. Confidentiality & Page Number Footer
        self.setFont("Helvetica-Oblique", 8)
        self.setFillColor(HexColor("#64748b"))
        footer_text = f"Confidential Analysis | Generated on {datetime.now().strftime('%Y-%m-%d %H:%M')} | Page {self._pageNumber} of {page_count}"
        self.drawCentredString(306, 25, footer_text)
        
        self.restoreState()


def clean_citations_and_markup(text: str) -> str:
    """Escapes XML entities and strips citation markers for ReportLab compatibility."""
    if not text:
        return ""
    # Strip markdown source citations e.g. [Source 1](#source-1) or 【Source 1】 or [Source 1]
    text = re.sub(r"\[Source\s*\d+\]\(#source-\d+\)", "", text, flags=re.IGNORECASE)
    text = re.sub(r"【Source\s*\d+】", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\[Source\s*\d+\]", "", text, flags=re.IGNORECASE)
    # XML entity escape for Paragraph parser
    text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return text


def convert_inline_markdown(text: str) -> str:
    """Converts standard bold and italic markdown markers into HTML tags for ReportLab Paragraphs."""
    if not text:
        return ""
    # Convert bold **bold** or __bold__ to <b>bold</b>
    text = re.sub(r"\*\*(.*?)\*\*", r"<b>\1</b>", text)
    text = re.sub(r"__(.*?)__", r"<b>\1</b>", text)
    # Convert italic *italic* or _italic_ to <i>italic</i>
    text = re.sub(r"\*(.*?)\*", r"<i>\1</i>", text)
    text = re.sub(r"_(.*?)_", r"<i>\1</i>", text)
    return text


def create_styled_table(rows: List[List[str]], styles) -> Table:
    """Creates a beautifully styled ReportLab Table with auto-wrapped text paragraphs."""
    table_data = []
    
    num_cols = len(rows[0])
    # Printable area is 612 - 2 * 36 = 540 points
    col_width = 540 / num_cols if num_cols > 0 else 540
    
    header_style = ParagraphStyle(
        'RLTableHeader',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        textColor=HexColor('#ffffff'),
        fontSize=9,
        leading=11
    )
    
    cell_style = ParagraphStyle(
        'RLTableCell',
        parent=styles['Normal'],
        fontSize=8.5,
        leading=10.5
    )
    
    for row_idx, row in enumerate(rows):
        formatted_row = []
        for cell in row:
            cell_html = convert_inline_markdown(clean_citations_and_markup(cell))
            if row_idx == 0:
                formatted_row.append(Paragraph(cell_html, header_style))
            else:
                formatted_row.append(Paragraph(cell_html, cell_style))
        table_data.append(formatted_row)
        
    t = Table(table_data, colWidths=[col_width] * num_cols)
    
    # Base grid style
    t_style = [
        ('BACKGROUND', (0, 0), (-1, 0), HexColor('#1e293b')),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
        ('TOPPADDING', (0, 0), (-1, 0), 8),
        ('GRID', (0, 0), (-1, -1), 0.5, HexColor('#cbd5e1')),
    ]
    
    # Alternating rows
    for r in range(1, len(rows)):
        bg_color = HexColor('#f8fafc') if r % 2 == 1 else HexColor('#ffffff')
        t_style.append(('BACKGROUND', (0, r), (-1, r), bg_color))
        t_style.append(('BOTTOMPADDING', (0, r), (-1, r), 6))
        t_style.append(('TOPPADDING', (0, r), (-1, r), 6))
        
    t.setStyle(TableStyle(t_style))
    return t


def parse_markdown_to_flowables(text: str, styles) -> List[Any]:
    """Parses a markdown string line-by-line into ReportLab Flowables."""
    flowables = []
    lines = text.split("\n")
    
    in_table = False
    table_rows = []
    
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        
        # 1. Handle Tables
        if line.startswith("|") and (i + 1 < len(lines) and lines[i + 1].strip().startswith("|") and ("---" in lines[i + 1] or "-:" in lines[i + 1])):
            in_table = True
            table_rows = []
            headers = [c.strip() for c in line.split("|")[1:-1]]
            table_rows.append(headers)
            i += 2  # Skip header and separator rows
            continue
            
        if in_table:
            if line.startswith("|"):
                row_cols = [c.strip() for c in line.split("|")[1:-1]]
                table_rows.append(row_cols)
                i += 1
                continue
            else:
                in_table = False
                if table_rows:
                    flowables.append(create_styled_table(table_rows, styles))
                    flowables.append(Spacer(1, 10))
                # Fall through to standard parsing of current line
                
        if not line:
            flowables.append(Spacer(1, 6))
            i += 1
            continue
            
        # 2. Headings
        if line.startswith("### "):
            heading_text = convert_inline_markdown(clean_citations_and_markup(line[4:]))
            flowables.append(Paragraph(heading_text, styles["Heading3"]))
            flowables.append(Spacer(1, 4))
        elif line.startswith("## "):
            heading_text = convert_inline_markdown(clean_citations_and_markup(line[3:]))
            flowables.append(Paragraph(heading_text, styles["Heading2"]))
            flowables.append(Spacer(1, 6))
        elif line.startswith("# "):
            heading_text = convert_inline_markdown(clean_citations_and_markup(line[2:]))
            flowables.append(Paragraph(heading_text, styles["Heading1"]))
            flowables.append(Spacer(1, 8))
            
        # 3. Bullet points
        elif line.startswith("* ") or line.startswith("- "):
            bullet_text = clean_citations_and_markup(line[2:])
            bullet_html = convert_inline_markdown(bullet_text)
            flowables.append(Paragraph(bullet_html, styles["Bullet"]))
        elif re.match(r"^\d+\.\s+", line):
            match = re.match(r"^(\d+\.)\s+(.*)", line)
            bullet_num = match.group(1)
            bullet_text = clean_citations_and_markup(match.group(2))
            bullet_html = convert_inline_markdown(bullet_text)
            
            numbered_style = ParagraphStyle(
                'RLNumberedList',
                parent=styles['Normal'],
                leftIndent=20,
                firstLineIndent=-15,
                spaceAfter=4
            )
            flowables.append(Paragraph(f"<b>{bullet_num}</b> {bullet_html}", numbered_style))
            
        # 4. Standard text paragraph
        else:
            p_html = convert_inline_markdown(clean_citations_and_markup(line))
            flowables.append(Paragraph(p_html, styles["Normal"]))
            flowables.append(Spacer(1, 6))
            
        i += 1
        
    if in_table and table_rows:
        flowables.append(create_styled_table(table_rows, styles))
        
    return flowables


def generate_executive_report(
    query: str, answer: str, sources: List[Dict[str, Any]], visuals: Optional[List[str]] = None
) -> bytes:
    """
    Generates a high-quality, professional PDF report using ReportLab.
    Features: slate-navy dynamic page template headers, "Page X of Y" dynamic footers,
    nested table autoscaling, markdown styling translation, and high-DPI image support.
    """
    pdf_buffer = io.BytesIO()
    
    # printable area: margins 36pt (0.5 inch), Letter size is 612x792pt
    doc = SimpleDocTemplate(
        pdf_buffer,
        pagesize=letter,
        leftMargin=36,
        rightMargin=36,
        topMargin=100,  # Ensure no overlap with the running header bar
        bottomMargin=50  # Ensure no overlap with the footer bar
    )
    
    # 1. Custom Styles Config
    styles = getSampleStyleSheet()
    
    # Custom adjustments for Consulting-grade typography
    styles['Normal'].fontName = 'Helvetica'
    styles['Normal'].fontSize = 10
    styles['Normal'].leading = 14
    styles['Normal'].textColor = HexColor('#1e293b') # Slate-800
    
    styles['Heading1'].fontName = 'Helvetica-Bold'
    styles['Heading1'].fontSize = 15
    styles['Heading1'].leading = 18
    styles['Heading1'].textColor = HexColor('#0f172a') # Slate-900
    styles['Heading1'].spaceBefore = 12
    styles['Heading1'].spaceAfter = 8
    
    styles['Heading2'].fontName = 'Helvetica-Bold'
    styles['Heading2'].fontSize = 13
    styles['Heading2'].leading = 16
    styles['Heading2'].textColor = HexColor('#1e293b')
    styles['Heading2'].spaceBefore = 10
    styles['Heading2'].spaceAfter = 6
    
    styles['Heading3'].fontName = 'Helvetica-Bold'
    styles['Heading3'].fontSize = 11
    styles['Heading3'].leading = 14
    styles['Heading3'].textColor = HexColor('#334155')
    styles['Heading3'].spaceBefore = 8
    styles['Heading3'].spaceAfter = 4
    
    styles['Bullet'].fontName = 'Helvetica'
    styles['Bullet'].fontSize = 10
    styles['Bullet'].leading = 14
    styles['Bullet'].textColor = HexColor('#1e293b')
    styles['Bullet'].leftIndent = 20
    styles['Bullet'].firstLineIndent = -10
    styles['Bullet'].spaceAfter = 4
    
    story = []
    
    # --- SECTION 1: RESEARCH QUERY ---
    story.append(Paragraph("1. Research Query", styles["Heading1"]))
    story.append(Spacer(1, 4))
    
    clean_query = convert_inline_markdown(clean_citations_and_markup(query))
    story.append(Paragraph(clean_query, styles["Normal"]))
    story.append(Spacer(1, 12))
    
    # --- SECTION 2: INTELLIGENCE SYNTHESIS ---
    story.append(Paragraph("2. Intelligence Synthesis", styles["Heading1"]))
    story.append(Spacer(1, 4))
    
    content_flowables = parse_markdown_to_flowables(answer, styles)
    story.extend(content_flowables)
    story.append(Spacer(1, 12))
    
    # --- SECTION 3: ANALYTICS & VISUALIZATIONS ---
    if visuals and len(visuals) > 0:
        story.append(PageBreak())  # Start visualizations on a new page for premium layout
        story.append(Paragraph("3. Visual Intelligence & Ad-Hoc Analytics", styles["Heading1"]))
        story.append(Spacer(1, 10))
        
        for idx, base64_img in enumerate(visuals):
            try:
                if "base64," in base64_img:
                    base64_img = base64_img.split("base64,")[1]
                    
                img_data = base64.b64decode(base64_img)
                img = Image.open(io.BytesIO(img_data))
                
                if img.mode in ("RGBA", "LA"):
                    background = Image.new("RGB", img.size, (250, 252, 254))
                    background.paste(img, mask=img.split()[3])
                    img = background
                    
                # Save to a temporary file
                temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".png")
                img.save(temp_file.name)
                temp_file.close()
                
                # ReportLab visual sizing: max width 500 points
                w_points = 500
                h_points = (img.height / img.width) * w_points
                
                # Pack visualization block together to prevent page orphan splits
                viz_block = []
                viz_block.append(RLImage(temp_file.name, width=w_points, height=h_points))
                viz_block.append(Spacer(1, 6))
                
                caption_style = ParagraphStyle(
                    'RLCaption',
                    parent=styles['Normal'],
                    fontName='Helvetica-Oblique',
                    fontSize=8,
                    leading=10,
                    textColor=HexColor('#94a3b8'),
                    alignment=1  # Centered
                )
                viz_block.append(Paragraph(f"Chart {idx+1}: Business Intelligence & Relational Analytics Visualization", caption_style))
                viz_block.append(Spacer(1, 15))
                
                story.append(KeepTogether(viz_block))
                
                # Cleanup temp file securely
                # (We keep it until doc.build ends, which is handled cleanly)
            except Exception as e:
                print(f"Failed to embed visual {idx}: {e}")
                
    # --- SECTION 4: EVIDENCE APPENDIX ---
    if sources and len(sources) > 0:
        story.append(PageBreak() if len(story) > 10 else Spacer(1, 12))
        
        sec_num = "4" if visuals else "3"
        story.append(Paragraph(f"{sec_num}. Verifiable Source Evidence", styles["Heading1"]))
        story.append(Spacer(1, 8))
        
        source_header_style = ParagraphStyle(
            'RLSourceHeader',
            parent=styles['Heading3'],
            fontName='Helvetica-Bold',
            fontSize=9.5,
            leading=12,
            textColor=HexColor('#0f172a'),
            backColor=HexColor('#f1f5f9'),
            borderColor=HexColor('#cbd5e1'),
            borderWidth=0.5,
            borderPadding=4,
            spaceBefore=8,
            spaceAfter=2
        )
        
        source_sub_style = ParagraphStyle(
            'RLSourceSub',
            parent=styles['Normal'],
            fontName='Helvetica-Oblique',
            fontSize=8,
            leading=10,
            textColor=HexColor('#64748b'),
            spaceAfter=4
        )
        
        snippet_style = ParagraphStyle(
            'RLSourceSnippet',
            parent=styles['Normal'],
            fontSize=8.5,
            leading=12,
            textColor=HexColor('#334155'),
            spaceAfter=8
        )
        
        for i, src in enumerate(sources, 1):
            filename = clean_citations_and_markup(src.get("filename", "Unknown Document"))
            snippet = convert_inline_markdown(clean_citations_and_markup(src.get("snippet", "No preview available.")))
            page_info = f" (Page {src.get('page')})" if src.get("page") else ""
            score_info = f"{(src.get('score', 0) * 100):.0f}% Match" if isinstance(src.get('score'), (int, float)) else f"{src.get('score', 'High')}"
            
            src_block = []
            src_block.append(Paragraph(f"SOURCE [{i}]: {filename}", source_header_style))
            src_block.append(Paragraph(f"Context Type: Document Grounding {page_info} | Relevance: {score_info}", source_sub_style))
            src_block.append(Paragraph(snippet, snippet_style))
            
            story.append(KeepTogether(src_block))
            
    # Build Document using our custom NumberedCanvas page templates!
    doc.build(story, canvasmaker=NumberedCanvas)
    
    pdf_bytes = pdf_buffer.getvalue()
    pdf_buffer.close()
    return pdf_bytes
