from typing import Any


def compute_confidence(
    answer: str, chunks: list[dict[str, Any]], graph_enrichment_used: bool
) -> dict[str, Any]:
    if not chunks:
        return {
            "confidence_score": 0.0,
            "citation_coverage": 0.0,
            "graph_enrichment_used": graph_enrichment_used,
            "weak_claims": ["No supporting sources were retrieved."],
        }

    top_scores = [float(chunk.get("score", 0.0)) for chunk in chunks[:5]]
    avg_score = sum(top_scores) / len(top_scores) if top_scores else 0.0
    chunk_factor = min(len(chunks) / 10, 1.0)
    graph_bonus = 0.05 if graph_enrichment_used else 0.0
    answer_factor = 0.1 if len(answer.strip()) > 200 else 0.0

    confidence_score = min(
        round((avg_score * 0.65) + (chunk_factor * 0.2) + graph_bonus + answer_factor, 4), 0.99
    )
    citation_coverage = round(min(len(chunks) / max(len(answer.splitlines()) or 1, 1), 1.0), 4)

    weak_claims: list[str] = []
    if avg_score < 0.45:
        weak_claims.append("Retrieved evidence is relatively weak for this answer.")
    if len(chunks) < 3:
        weak_claims.append("Answer is supported by a limited number of source chunks.")

    return {
        "confidence_score": confidence_score,
        "citation_coverage": citation_coverage,
        "graph_enrichment_used": graph_enrichment_used,
        "weak_claims": weak_claims,
    }
