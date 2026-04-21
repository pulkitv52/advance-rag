import re

from src.services.reporting import cleanup_html_for_fpdf


def test_cleanup_html_flattens_table_cells_to_plain_text():
    html = "<table><tr><td>Alpha<br/>Beta<ul><li>Gamma</li></ul></td><th><strong>Header</strong><br><em>Line</em></th></tr></table>"

    cleaned = cleanup_html_for_fpdf(html)

    assert "<br" not in cleaned.lower()
    assert "<td>Alpha | Beta * Gamma</td>" in cleaned
    assert "<th>Header | Line</th>" in cleaned

    for cell in re.findall(
        r"<(?:td|th)[^>]*>(.*?)</(?:td|th)>", cleaned, flags=re.IGNORECASE | re.DOTALL
    ):
        assert "<" not in cell
        assert ">" not in cell
