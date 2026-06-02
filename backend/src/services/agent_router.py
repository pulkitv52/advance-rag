"""
Agentic Router and Safe Text-to-Cypher generation service.
"""

import json
import re
from typing import Any, Dict, Optional
from src.core.config import get_settings
from src.core.logger import logger
from src.services.nvidia import _get_nim_client

settings = get_settings()

ROUTER_SYSTEM_PROMPT = (
    "You are an elite AI Query Router for a state-level social welfare intelligence platform.\n"
    "Your task is to analyze the user's query and classify it into one of three routes:\n"
    "1. 'DYNAMIC_CYPHER': Choose this if the query asks for aggregate statistics, counts, lists, geographic patterns, or relational queries on the citizen database (e.g., 'How many citizens are enrolled in scheme S767?', 'List all flagged citizens in Jalpaiguri', 'Find duplicates in GP SIKARPUR'). Do NOT choose this for simple single-citizen detail checks (handled separately).\n"
    "2. 'HYBRID': Choose this if the query requires combining BOTH statistical or relational database lookups AND policy document verification (e.g., 'Check which scheme Pumy Mraol is enrolled in and explain if she meets the eligibility criteria according to the scheme manual', 'For citizen 455920445527 check scheme and explain its benefits').\n"
    "3. 'DOCUMENT_RAG': Choose this for any questions about rules, guidelines, eligibility criteria, definitions, scheme details from PDF manuals, general system questions, greetings, or when no database search is needed (e.g., 'What is the vulnerability score limit?', 'Tell me about the Banglar Bari scheme', 'Hi').\n\n"
    "You must return your classification in strict JSON format with the following keys:\n"
    "- 'route': 'DOCUMENT_RAG' | 'DYNAMIC_CYPHER' | 'HYBRID'\n"
    "- 'explanation': 'A brief sentence explaining the choice of route.'\n"
    "- 'extracted_params': {\n"
    "    'uid': string or null (12-digit numeric UID),\n"
    "    'name': string or null (extracted person name),\n"
    "    'scheme_id': string or null (extracted scheme ID like S767)\n"
    "  }\n"
    "Do not include any formatting, text, or markdown code blocks (like ```json) in your response, output raw valid JSON only."
)

CYPHER_GENERATOR_PROMPT = (
    "You are an expert Neo4j Cypher developer. Translate the user's natural language question into a high-performance, read-only Cypher query based on the database schema provided below.\n\n"
    "### Graph Schema Database Model:\n"
    "Nodes:\n"
    "- (c:Citizen {uid: String, name: String, risk_tier: String, vulnerability_score: Integer, mobile: String, dob: String, is_ghost_flag: Boolean, is_dup_flag: Boolean, is_anomaly_flag: Boolean})\n"
    "- (s:Scheme {id: String, name: String, type: String, department: String, description: String})\n"
    "- (f:FraudFlag {rule: String, type: String, description: String, confidence: Integer})\n"
    "- (g:GP {name: String})\n"
    "- (b:Block {name: String})\n"
    "- (d:District {name: String})\n\n"
    "Relationships:\n"
    "- (c)-[:ENROLLED_IN]->(s)           (Citizen is enrolled in a Scheme)\n"
    "- (c)-[:RESIDES_IN]->(g)            (Citizen resides in a GP)\n"
    "- (g)-[:PART_OF]->(b)               (GP is part of a Block)\n"
    "- (b)-[:PART_OF]->(d)               (Block is part of a District)\n"
    "- (c)-[:FLAGGED_AS]->(f)            (Citizen is flagged as Fraud)\n"
    "- (c)-[:POTENTIAL_DUPLICATE]-(c2:Citizen) (Citizen is a potential duplicate of another)\n\n"
    "### Cypher Writing Guidelines:\n"
    "1. Output ONLY the raw Cypher query inside ```cypher ... ``` code block. Do not write any other explanation or text.\n"
    "2. Be careful with relationship directions. Use: `(c)-[:ENROLLED_IN]->(s)`, `(c)-[:RESIDES_IN]->(g)`, `(g)-[:PART_OF]->(b)`, `(b)-[:PART_OF]->(d)`, `(c)-[:FLAGGED_AS]->(f)`.\n"
    "3. Use case-insensitive matches for geographical names, citizen names, or titles. For example: `WHERE toLower(g.name) = toLower('SIKARPUR')` or `WHERE toLower(c.name) CONTAINS toLower('pramila')`.\n"
    "4. For aggregate queries, write standard read-only statements using MATCH, WHERE, RETURN, ORDER BY, LIMIT, count(), sum(), avg(), etc.\n"
    "5. Ensure any lookup has a limit of maximum 100 records if returning individual lists.\n"
    "6. Make sure to alias return variables cleanly (e.g. `RETURN count(c) AS citizen_count` or `RETURN c.name AS name, c.uid AS uid`).\n"
    "7. CRITICAL: Do NOT generate parameterized queries using $ placeholders (e.g. $schemeId, $gpName). You MUST output exact matching query values inside standard single quotes (e.g. {id: 'S767'} or WHERE toLower(g.name) = 'sikarpur'). If the query does not supply a specific value and no context is provided, write a generic match without the property filter.\n"
    "8. Scheme fuzzy match: If a user specifies a scheme by name (e.g. 'swasthya scheme') and it is not in the conversational context as a specific ID (like 'S767'), you MUST use case-insensitive fuzzy matches instead of exact property maps. For example, use: `WHERE toLower(s.name) CONTAINS 'swasthya'` or `WHERE toLower(s.name) CONTAINS toLower('swasthya')` rather than `{name: 'swasthya'}` (Note: in our database, s.name is usually set to the scheme ID, so exact property matching on names will fail).\n\n"
    "### Examples:\n"
    "- 'How many citizens are enrolled in scheme S767?'\n"
    "  ```cypher\n"
    "  MATCH (c:Citizen)-[:ENROLLED_IN]->(s:Scheme {id: 'S767'})\n"
    "  RETURN count(c) AS total_enrolled\n"
    "  ```\n"
    "- 'List all flagged citizens in Jalpaiguri district'\n"
    "  ```cypher\n"
    "  MATCH (c:Citizen)-[:FLAGGED_AS]->(f:FraudFlag)\n"
    "  MATCH (c)-[:RESIDES_IN]->(g:GP)-[:PART_OF]->(b:Block)-[:PART_OF]->(d:District)\n"
    "  WHERE toLower(d.name) = 'jalpaiguri'\n"
    "  RETURN c.name AS name, c.uid AS uid, collect(f.rule) AS flags, d.name AS district LIMIT 50\n"
    "  ```\n"
    "- 'Show top 5 vulnerable citizens in block RAJGANJ'\n"
    "  ```cypher\n"
    "  MATCH (c:Citizen)-[:RESIDES_IN]->(g:GP)-[:PART_OF]->(b:Block {name: 'RAJGANJ'})\n"
    "  RETURN c.name AS name, c.uid AS uid, c.vulnerability_score AS score\n"
    "  ORDER BY c.vulnerability_score DESC LIMIT 5\n"
    "  ```\n"
)


def resolve_scheme_id_by_name(query: str) -> Optional[str]:
    """
    Fuzzy maps friendly scheme names to database scheme IDs (like S767 for Swasthya Sathi).
    """
    q = query.lower()
    # Clean the query of any invisible characters or standard typos (like "cheme", "schme")
    q_clean = re.sub(r"[^a-z0-9\s]", "", q)
    if "swasthya" in q_clean or "sathi" in q_clean or "swastha" in q_clean or "swasth" in q_clean:
        return "S767"
    return None


async def route_query(query: str, history: Optional[list] = None) -> Dict[str, Any]:
    """
    Routes query using Llama 70B Instruct LLM.
    Returns:
      {
         "route": "DOCUMENT_RAG" | "DYNAMIC_CYPHER" | "HYBRID",
         "explanation": str,
         "extracted_params": {"uid": str|None, "name": str|None, "scheme_id": str|None}
      }
    """
    client = _get_nim_client()
    messages = [
        {"role": "system", "content": ROUTER_SYSTEM_PROMPT},
    ]
    if history:
        messages.extend(history)
    messages.append({"role": "user", "content": f"Query: {query}"})

    try:
        response = await client.chat.completions.create(
            model=settings.NIM_LLM_MODEL,
            messages=messages,
            temperature=0.0,
            max_tokens=500,
        )
        content = response.choices[0].message.content.strip()
        
        # Clean up any potential markdown code blocks returned by mistake
        content_clean = re.sub(r"^```(?:json)?\s*|\s*```$", "", content, flags=re.MULTILINE).strip()
        parsed = json.loads(content_clean)
        
        # Ensure extracted_params dict is present
        if "extracted_params" not in parsed or not isinstance(parsed["extracted_params"], dict):
            parsed["extracted_params"] = {"uid": None, "name": None, "scheme_id": None}
            
        # Inject fuzzy scheme_id resolution if missing
        if not parsed["extracted_params"].get("scheme_id"):
            resolved = resolve_scheme_id_by_name(query)
            if resolved:
                parsed["extracted_params"]["scheme_id"] = resolved
                logger.info(f"[ROUTER AGENT] Fuzzy resolved friendly scheme name to ID: {resolved}")
                
        logger.info(f"[ROUTER AGENT] Successfully routed query to {parsed.get('route')} - explanation: {parsed.get('explanation')}")
        return parsed
    except Exception as e:
        logger.error(f"[ROUTER AGENT] Router execution failed: {e}. Defaulting to DOCUMENT_RAG.")
        return {
            "route": "DOCUMENT_RAG",
            "explanation": f"Routing failed with error: {str(e)}. Fallback to Document RAG.",
            "extracted_params": {"uid": None, "name": None, "scheme_id": None}
        }


async def generate_cypher(query: str, extracted_params: Optional[Dict[str, Any]] = None) -> Optional[str]:
    """
    Generates a read-only Cypher query based on natural language user query and resolved entities context.
    """
    client = _get_nim_client()
    
    context_str = ""
    if extracted_params:
        non_null = {k: v for k, v in extracted_params.items() if v}
        if non_null:
            context_str = (
                "\nConversational Context (MUST use these exact values directly in your query filters instead of parameter placeholders like $schemeId):\n" 
                + "\n".join(f"- {k}: {v}" for k, v in non_null.items())
            )
            
    messages = [
        {"role": "system", "content": CYPHER_GENERATOR_PROMPT},
        {"role": "user", "content": f"Question: {query}{context_str}\n\nGenerate Cypher:"}
    ]

    try:
        response = await client.chat.completions.create(
            model=settings.NIM_LLM_MODEL,
            messages=messages,
            temperature=0.0,
            max_tokens=1000,
        )
        content = response.choices[0].message.content.strip()
        
        # Extract Cypher from code blocks
        cypher_match = re.search(r"```cypher\s*(.*?)\s*```", content, re.DOTALL | re.IGNORECASE)
        if cypher_match:
            cypher = cypher_match.group(1).strip()
        else:
            # Fallback to general code blocks or entire text
            code_match = re.search(r"```\s*(.*?)\s*```", content, re.DOTALL)
            cypher = code_match.group(1).strip() if code_match else content
            
        logger.info(f"[ROUTER AGENT] Generated Cypher: {cypher}")
        return cypher
    except Exception as e:
        logger.error(f"[ROUTER AGENT] Cypher generation failed: {e}")
        return None


async def repair_cypher(
    query: str,
    failed_cypher: str,
    execution_error: str,
    extracted_params: Optional[Dict[str, Any]] = None,
) -> Optional[str]:
    """
    Regenerate Cypher after Neo4j execution failure by feeding the exact error
    back to the LLM and asking for a corrected read-only query.
    """
    client = _get_nim_client()

    context_str = ""
    if extracted_params:
        non_null = {k: v for k, v in extracted_params.items() if v}
        if non_null:
            context_str = (
                "\nConversational Context (MUST use these exact values directly in your query filters):\n"
                + "\n".join(f"- {k}: {v}" for k, v in non_null.items())
            )

    repair_prompt = (
        f"Question: {query}{context_str}\n\n"
        "The previous Cypher failed in Neo4j. Fix it and return ONLY corrected read-only Cypher.\n\n"
        f"Failed Cypher:\n```cypher\n{failed_cypher}\n```\n\n"
        f"Neo4j Error:\n{execution_error}\n\n"
        "Requirements:\n"
        "- Keep query strictly read-only.\n"
        "- Preserve user intent exactly.\n"
        "- Use functions/operators supported by Neo4j.\n"
        "- Return only a Cypher code block.\n"
    )

    try:
        response = await client.chat.completions.create(
            model=settings.NIM_LLM_MODEL,
            messages=[
                {"role": "system", "content": CYPHER_GENERATOR_PROMPT},
                {"role": "user", "content": repair_prompt},
            ],
            temperature=0.0,
            max_tokens=1000,
        )
        content = response.choices[0].message.content.strip()
        cypher_match = re.search(r"```cypher\s*(.*?)\s*```", content, re.DOTALL | re.IGNORECASE)
        if cypher_match:
            cypher = cypher_match.group(1).strip()
        else:
            code_match = re.search(r"```\s*(.*?)\s*```", content, re.DOTALL)
            cypher = code_match.group(1).strip() if code_match else content

        logger.info(f"[ROUTER AGENT] Repaired Cypher: {cypher}")
        return cypher
    except Exception as e:
        logger.error(f"[ROUTER AGENT] Cypher repair failed: {e}")
        return None


def is_cypher_safe(query: str) -> bool:
    """
    Strict sandbox checker. Returns True if read-only, False if mutating keywords are present.
    Strips string literals first to prevent bypasses inside quotes.
    """
    # Remove strings inside quotes
    clean_q = re.sub(r'["\'].*?["\']', '', query.lower())
    destructive_keywords = [
        r"\bcreate\b", r"\bmerge\b", r"\bdelete\b", r"\bset\b", 
        r"\bremove\b", r"\bdetach\b", r"\bdrop\b", r"\bload\b", r"\bwrite\b"
    ]
    for kw in destructive_keywords:
        if re.search(kw, clean_q):
            logger.warning(f"[SANDBOX] Blocked Cypher query due to forbidden keyword matching pattern '{kw}': {query}")
            return False
    return True
