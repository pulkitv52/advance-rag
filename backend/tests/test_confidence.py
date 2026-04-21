from src.services.confidence import compute_confidence


def test_compute_confidence_with_supporting_chunks():
    chunks = [
        {"score": 0.92},
        {"score": 0.87},
        {"score": 0.81},
    ]

    result = compute_confidence(
        "Detailed grounded answer with enough supporting evidence.", chunks, True
    )

    assert result["confidence_score"] is not None
    assert result["confidence_score"] > 0.5
    assert result["citation_coverage"] >= 0.0
    assert result["graph_enrichment_used"] is True


def test_compute_confidence_flags_weak_support():
    result = compute_confidence("Short answer.", [{"score": 0.12}], False)

    assert result["confidence_score"] < 0.5
    assert len(result["weak_claims"]) >= 1
