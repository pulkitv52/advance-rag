"""Tests for the ingestion processor: chunking logic."""

import pytest

from src.services.processor import _chunk_elements


def test_chunk_empty_input():
    assert _chunk_elements([]) == []


def test_chunk_single_paragraph():
    elements = [{"type": "paragraph", "text": "Hello world", "page": 1}]
    chunks = _chunk_elements(elements)
    assert len(chunks) == 1
    assert "Hello world" in chunks[0]["text"]


def test_tables_kept_intact():
    elements = [
        {"type": "table", "text": "| A | B |\n|---|---|\n| 1 | 2 |", "page": 1},
    ]
    chunks = _chunk_elements(elements)
    assert len(chunks) == 1
    assert chunks[0]["element_type"] == "table"


def test_large_text_is_split():
    long_text = "word " * 500  # ~2500 chars
    elements = [{"type": "paragraph", "text": long_text, "page": 1}]
    chunks = _chunk_elements(elements, max_chars=1000)
    assert len(chunks) >= 2


def test_chunk_index_assigned():
    elements = [
        {"type": "paragraph", "text": "First paragraph.", "page": 1},
        {"type": "paragraph", "text": "Second paragraph.", "page": 1},
    ]
    chunks = _chunk_elements(elements)
    for i, chunk in enumerate(chunks):
        assert chunk["chunk_index"] == i


def test_heading_flushed_separately():
    elements = [
        {"type": "heading", "text": "Chapter 1", "page": 1},
        {"type": "paragraph", "text": "Content after heading.", "page": 1},
    ]
    chunks = _chunk_elements(elements)
    heading_chunks = [c for c in chunks if c.get("element_type") == "heading"]
    assert len(heading_chunks) == 1
    assert heading_chunks[0]["text"] == "Chapter 1"
