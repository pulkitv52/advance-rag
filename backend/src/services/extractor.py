import json
import re
from typing import Any, Dict, List, Optional

from src.core.config import get_settings
from src.core.logger import logger
from src.services import nvidia

settings = get_settings()

TRIPLET_EXTRACTION_PROMPT = """
-Goal-
Given a text document (which may contain raw LaTeX formatting or structural table markers like \icolumn, \begin{{table}}, etc.), identify all entities and their entity types from the text and all relationships among the identified entities.
Ignore the LaTeX formatting markers and focus on the semantic information within.
All proper nouns must be extracted as entities. Example: a filename, book, person, organization, etc.
Given the text, extract up to {max_knowledge_triplets} entity-relation triplets.

-Steps-
1. Identify all entities. For each identified entity, extract:
   - entity_name: Name of the entity, capitalized
   - entity_type: Type of the entity. PREFERRED TYPES: ['Person', 'Organization', 'Location', 'Event', 'Concept', 'Document']. Choose the closest standard category.
   - entity_description: Comprehensive description of attributes and activities

2. Identify pairs of (source_entity, target_entity) that are *clearly related*.
   For each relationship, extract:
   - source_entity: name of the source entity
   - target_entity: name of the target entity
   - relation: relationship between them (e.g., "WORKS_FOR", "LOCATED_IN", "PARTNERS_WITH")
   - relationship_description: why they are related. Mention context from the text.

3. Output Format:
   Return a valid JSON object with keys 'entities' and 'relationships'.
   NO other text or explanations.

-Output Example-
{{
  "entities": [
    {{ "entity_name": "Albert Einstein", "entity_type": "Person", "entity_description": "Theoretical physicist..." }}
  ],
  "relationships": [
    {{ "source_entity": "Albert Einstein", "target_entity": "Theory of Relativity", "relation": "DEVELOPED", "relationship_description": "Einstein is the developer..." }}
  ]
}}
"""


def _repair_json(text: str) -> str:
    """
    Attempts to repair common LLM JSON formatting errors like missing commas
    between objects or trailing commas.
    """
    # Fix missing commas between closing brace and opening brace of next object
    text = re.sub(r"\}\s*\{", "}, {", text)
    # Fix missing commas between closing bracket and opening bracket
    text = re.sub(r"\]\s*\[", "], [", text)
    # Remove trailing commas before closing braces/brackets
    text = re.sub(r",\s*\}", "}", text)
    text = re.sub(r",\s*\]", "]", text)
    return text


async def extract_triplets(text: str, max_triplets: int = 20) -> List[Dict[str, Any]]:
    """
    Uses the 120B LLM to extract knowledge triplets from a text chunk.
    Splits very large text blocks into smaller pieces to avoid truncation errors.
    """
    # Threshold for sub-chunking (chars)
    TEXT_LIMIT = 4000

    if len(text) > TEXT_LIMIT:
        logger.info(
            f"Text too large ({len(text)} chars). Splitting into sub-chunks for extraction."
        )
        # Simple split by newline if possible
        parts = []
        current_part = ""
        for line in text.split("\n"):
            if len(current_part) + len(line) < TEXT_LIMIT:
                current_part += line + "\n"
            else:
                parts.append(current_part)
                current_part = line + "\n"
        if current_part:
            parts.append(current_part)

        all_triplets = []
        for part in parts:
            # Strictly limit to 5 triplets to keep JSON short and reliable
            part_triplets = await _extract_single_block(part, max_triplets=5)
            all_triplets.extend(part_triplets)
        return all_triplets
    else:
        return await _extract_single_block(text, max_triplets=max_triplets)


async def _extract_single_block(text: str, max_triplets: int = 20) -> List[Dict[str, Any]]:
    """Internal helper to extract triplets from a single manageable text block."""
    try:
        system_prompt = TRIPLET_EXTRACTION_PROMPT.format(max_knowledge_triplets=max_triplets)

        response = await nvidia.generate_rag_answer(
            query=f"Extract knowledge triplets from the following text:\n\n{text}",
            context_chunks=[],
            model_override=settings.NIM_LLM_MODEL,
            system_prompt=system_prompt,
        )

        logger.info(f"Extraction response received (length: {len(response)})")

        # Find the outermost JSON object
        start_idx = response.find("{")
        end_idx = response.rfind("}")

        if start_idx == -1 or end_idx == -1:
            return []

        json_str = response[start_idx : end_idx + 1]

        try:
            data = json.loads(json_str)
        except json.JSONDecodeError:
            logger.info("Attempting to repair malformed JSON response...")
            repaired_json = _repair_json(json_str)
            try:
                data = json.loads(repaired_json)
            except:
                logger.error("JSON repair failed.")
                return []

        rel_list = data.get("relationships", [])
        ent_list = data.get("entities", [])

        # Create a case-insensitive lookup for entity types
        # This prevents issues where 'vibhu' is a relation source but 'Vibhu' is the entity name
        entity_types = {
            str(e.get("entity_name")).lower(): e.get("entity_type", "Entity") for e in ent_list
        }

        triplets = []
        for rel in rel_list:
            s_name = rel.get("source_entity")
            t_name = rel.get("target_entity")
            if s_name and t_name:
                triplets.append(
                    {
                        "source": str(s_name),
                        "source_type": str(entity_types.get(str(s_name).lower(), "Entity")),
                        "target": str(t_name),
                        "target_type": str(entity_types.get(str(t_name).lower(), "Entity")),
                        "relation": str(rel.get("relation", "RELATED")),
                        "description": str(rel.get("relationship_description", "")),
                    }
                )

        return triplets

    except Exception as e:
        logger.error(f"Failed to extract triplets from block: {e}")
        return []


async def extract_entities_from_query(query: str) -> List[str]:
    """
    Extracts potential entities from a user query to use for graph-based retrieval enrichment.
    """
    prompt = (
        "Extract the main specific entities (people, projects, organizations, technologies) from the following query. "
        "Return ONLY a JSON list of strings representing these entities. "
        "Clean the names of any common filler words or punctuation. "
        "Example: 'vibhu role in cp grams' -> ['Vibhu', 'CP Grams']"
    )

    try:
        response = await nvidia.generate_rag_answer(
            query=f"Query: {query}",
            context_chunks=[],
            model_override=settings.NIM_LLM_MODEL,
            system_prompt=prompt,
        )

        # Clean response string to find JSON
        match = re.search(r"\[.*\]", response, re.DOTALL)
        if match:
            return json.loads(match.group(0))
    except:
        pass

    # Fallback to simple split if LLM fails or is too slow for tiny queries
    return query.lower().split()
