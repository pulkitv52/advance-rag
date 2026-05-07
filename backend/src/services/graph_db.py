import asyncio
from typing import Any, Dict, List, Optional

from neo4j import AsyncGraphDatabase

from src.core.config import get_settings
from src.core.logger import logger

settings = get_settings()

_driver = None


async def get_driver():
    global _driver
    if _driver is None:
        _driver = AsyncGraphDatabase.driver(
            settings.NEO4J_URI, auth=(settings.NEO4J_USER, settings.NEO4J_PASSWORD)
        )
    return _driver


async def close_driver():
    global _driver
    if _driver is not None:
        await _driver.close()
        _driver = None


async def save_triplets(document_id: str, triplets: List[Dict[str, Any]]):
    """
    Saves extracted triplets into Neo4j.
    Triplet format: { "source": "...", "source_type": "...", "target": "...", "target_type": "...", "relation": "...", "description": "..." }
    """
    driver = await get_driver()
    async with driver.session() as session:
        # We use :Entity as a base label and store the specific type in a property for flexible coloring
        query = """
        UNWIND $triplets AS triplet
        MERGE (s:Entity {name: triplet.source})
        ON CREATE SET s.document_ids = [$document_id], s.created_at = datetime(), s.type = coalesce(triplet.source_type, "Entity")
        ON MATCH SET s.document_ids = apoc.coll.toSet(coalesce(s.document_ids, []) + $document_id),
                     s.type = coalesce(triplet.source_type, s.type, "Entity")

        MERGE (t:Entity {name: triplet.target})
        ON CREATE SET t.document_ids = [$document_id], t.created_at = datetime(), t.type = coalesce(triplet.target_type, "Entity")
        ON MATCH SET t.document_ids = apoc.coll.toSet(coalesce(t.document_ids, []) + $document_id),
                     t.type = coalesce(triplet.target_type, t.type, "Entity")

        MERGE (s)-[r:RELATED {type: triplet.relation}]->(t)
        ON CREATE SET r.description = triplet.description, r.document_ids = [$document_id]
        ON MATCH SET r.document_ids = apoc.coll.toSet(coalesce(r.document_ids, []) + $document_id)
        """
        try:
            await session.run(query, triplets=triplets, document_id=document_id)
            logger.info(f"Saved {len(triplets)} triplets to Neo4j for document {document_id}")
        except Exception as e:
            logger.error(f"Failed to save triplets to Neo4j: {e}")


async def get_combined_graph(
    document_ids: Optional[List[str]] = None, entities: Optional[List[str]] = None
) -> Dict[str, List[Dict[str, Any]]]:
    """
    Retrieves nodes and edges for visualization.
    If traditional Document Graph edges (:RELATED) exist, returns document graph.
    Otherwise, returns the USR Fraud Intelligence graph.
    """
    try:
        driver = await get_driver()
        async with driver.session() as session:
            # Fast existence check — if no RELATED edges exist, it's a USR graph
            check_result = await session.run(
                "MATCH ()-[r:RELATED]->() RETURN count(r) AS cnt LIMIT 1"
            )
            check_record = await check_result.single()

            # The Knowledge Map should default to the USR intelligence graph
            # unless the caller explicitly scopes the request to documents.
            # This prevents stray text in the research query box from
            # unintentionally switching the map into an empty document-graph view.
            force_usr_view = not document_ids

            if force_usr_view or not check_record or check_record["cnt"] == 0:
                logger.info("Knowledge Graph: formatting USR Fraud Intelligence Graph.")
                # Storytelling Graph: Fraudulent Citizens + Contextual Clean Citizens
                query = """
                MATCH (c:Citizen)
                OPTIONAL MATCH (c)-[:RESIDES_IN]->(gp:GP)-[:PART_OF]->(b:Block)-[:PART_OF]->(d:District)
                WITH c, gp, b, d,
                     CASE
                        WHEN (
                            c.is_ghost_flag = true
                            OR c.is_dup_flag = true
                            OR c.is_anomaly_flag = true
                            OR c.risk_tier IN ['HIGH', 'CRITICAL']
                            OR EXISTS { (c)-[:FLAGGED_AS]->(:FraudFlag) }
                        )
                        THEN 1 ELSE 0
                     END AS priority_score
                ORDER BY priority_score DESC, coalesce(c.vulnerability_score, 0) DESC
                LIMIT 400

                OPTIONAL MATCH (c)-[enroll:ENROLLED_IN]->(s:Scheme)
                OPTIONAL MATCH (c)-[dup:POTENTIAL_DUPLICATE]->(c2:Citizen)
                OPTIONAL MATCH (c)-[flag_edge:FLAGGED_AS]->(f:FraudFlag)
                
                RETURN properties(c) AS c, properties(gp) AS gp, properties(b) AS b, properties(d) AS d, 
                       properties(s) AS s, properties(enroll) AS enroll, properties(dup) AS dup, 
                       properties(c2) AS c2, properties(flag_edge) AS flag_edge, properties(f) AS f
                """
                result = await session.run(query)
                records = await result.data()

                if not records:
                    # Fallback to general hierarchy if no fraud detected yet
                    result = await session.run("""
                        MATCH (c:Citizen)-[:RESIDES_IN]->(gp:GP)-[:PART_OF]->(b:Block)-[:PART_OF]->(d:District)
                        RETURN properties(c) AS c, properties(gp) AS gp, properties(b) AS b, properties(d) AS d 
                        LIMIT 150
                    """)
                    records = await result.data()

                nodes = {}
                links = []

                def add_node(obj_id, label, node_type, properties=None):
                    if not obj_id:
                        return
                    if obj_id not in nodes:
                        nodes[obj_id] = {
                            "id": obj_id,
                            "label": label,
                            "type": node_type,
                            **(properties or {}),
                        }

                def add_link(source, target, label, description=""):
                    if not source or not target:
                        return
                    # Avoid duplicate links
                    if not any(
                        l["source"] == source and l["target"] == target and l["label"] == label
                        for l in links
                    ):
                        links.append(
                            {
                                "source": source,
                                "target": target,
                                "label": label,
                                "description": description,
                            }
                        )

                for rec in records:
                    c = rec.get("c")
                    gp = rec.get("gp")
                    b = rec.get("b")
                    d = rec.get("d")
                    s = rec.get("s")

                    if not c:
                        continue

                    # 1. Geographic Hierarchy
                    add_node(
                        d.get("code") if d else None,
                        d.get("name", "District") if d else "",
                        "District",
                    )
                    add_node(
                        b.get("code") if b else None, b.get("name", "Block") if b else "", "Block"
                    )
                    add_node(
                        gp.get("code") if gp else None, gp.get("name", "GP") if gp else "", "GP"
                    )

                    # Citizen node (mark red if risk-tier or explicitly fraud-flagged)
                    c_type = (
                        "FraudFlag"
                        if (c.get("risk_tier") in ["HIGH", "CRITICAL"] or rec.get("f"))
                        else "Citizen"
                    )
                    add_node(
                        c["uid"],
                        c.get("name", "Unknown"),
                        c_type,
                        {"risk_tier": c.get("risk_tier", "LOW")},
                    )

                    # Geographic links
                    if d and b and d.get("code") and b.get("code"):
                        add_link(b["code"], d["code"], "PART_OF")
                    if b and gp and b.get("code") and gp.get("code"):
                        add_link(gp["code"], b["code"], "PART_OF")
                    if gp and c and gp.get("code") and c.get("uid"):
                        add_link(c["uid"], gp["code"], "RESIDES_IN")

                    # 2. Scheme Enrollment
                    if s and c:
                        add_node(s["id"], s.get("name", "Scheme"), "Scheme")
                        add_link(c["uid"], s["id"], "ENROLLED_IN", "Status: Active")

                    # 3. Fraud Patterns
                    dup = rec.get("dup")
                    c2 = rec.get("c2")
                    if dup and c2:
                        c2_type = (
                            "FraudFlag"
                            if c2.get("risk_tier") in ["HIGH", "CRITICAL"]
                            else "Citizen"
                        )
                        add_node(
                            c2["uid"],
                            c2.get("name", "Unknown"),
                            c2_type,
                            {"risk_tier": c2.get("risk_tier", "LOW")},
                        )
                        add_link(
                            c["uid"],
                            c2["uid"],
                            "POTENTIAL_DUPLICATE",
                            f"Rule: {dup.get('rule')} ({dup.get('confidence')}%)",
                        )

                    flag_edge = rec.get("flag_edge")
                    f = rec.get("f")
                    if flag_edge and f:
                        f_id = f"FLAG_{f.get('rule')}_{f.get('type')}"
                        add_node(f_id, f"{f.get('type')}: {f.get('description')}", "FraudFlag")
                        add_link(
                            c["uid"], f_id, "FLAGGED_AS", f"Conf: {flag_edge.get('confidence')}%"
                        )

                    risk = rec.get("risk")
                    s = rec.get("s")
                    if risk and s:
                        if s.get("id") not in nodes:
                            nodes[s["id"]] = {
                                "id": s["id"],
                                "label": s.get("name", "Scheme"),
                                "type": "Scheme",
                            }
                        if not any(
                            l["source"] == gp["code"] and l["target"] == s["id"] for l in links
                        ):
                            links.append(
                                {
                                    "source": gp["code"],
                                    "target": s["id"],
                                    "label": "HIGH_RISK_CLUSTER",
                                    "description": f"Ratio: {risk.get('concentration_ratio')}",
                                }
                            )

                if not nodes:
                    return {
                        "nodes": [],
                        "links": [],
                        "message": "No document knowledge graph loaded. Upload a document to build the graph.",
                    }

                # Sort nodes to put FraudFlag last (so they render on top in the UI)
                sorted_nodes = sorted(
                    nodes.values(), key=lambda x: 1 if x.get("type") == "FraudFlag" else 0
                )

                return {"nodes": sorted_nodes, "links": links}

            # Original Document Graph logic below...
            if entities:
                query = """
                MATCH (s:Entity)
                WHERE any(e IN $entities WHERE s.name =~ ("(?i).*" + e + ".*"))
                MATCH (s)-[r:RELATED]-(t:Entity)
                """
                if document_ids:
                    query += " WHERE any(docId IN $document_ids WHERE docId IN coalesce(s.document_ids, [])) "

                query += """
                RETURN s.name AS source, t.name AS target, r.type AS relation, r.description AS description,
                       s.type as source_type, t.type as target_type
                LIMIT 100
                """
            elif document_ids:
                query = """
                MATCH (s:Entity)-[r:RELATED]->(t:Entity)
                WHERE any(docId IN $document_ids WHERE docId IN coalesce(s.document_ids, []))
                   OR any(docId IN $document_ids WHERE docId IN coalesce(t.document_ids, []))
                RETURN s.name AS source, t.name AS target, r.type AS relation, r.description AS description,
                       s.type as source_type, t.type as target_type
                LIMIT 200
                """
            else:
                query = """
                MATCH (s:Entity)-[r:RELATED]->(t:Entity)
                RETURN s.name AS source, t.name AS target, r.type AS relation, r.description AS description,
                       s.type as source_type, t.type as target_type
                LIMIT 200
                """

            result = await session.run(query, document_ids=document_ids, entities=entities)
            records = await result.data()

            nodes = {}
            links = []

            for rec in records:
                s_name = rec["source"]
                t_name = rec["target"]

                if s_name not in nodes:
                    nodes[s_name] = {
                        "id": s_name,
                        "label": s_name,
                        "type": rec.get("source_type", "Entity"),
                    }
                if t_name not in nodes:
                    nodes[t_name] = {
                        "id": t_name,
                        "label": t_name,
                        "type": rec.get("target_type", "Entity"),
                    }

                links.append(
                    {
                        "source": s_name,
                        "target": t_name,
                        "label": rec["relation"],
                        "description": rec["description"],
                    }
                )

            return {"nodes": list(nodes.values()), "links": links}
    except Exception as e:
        logger.warning(f"Knowledge graph unavailable, returning empty graph: {e}")
        return {"nodes": [], "links": []}


async def search_multi_hop_context(
    entities: List[str], document_ids: Optional[List[str]] = None
) -> List[str]:
    """
    Advanced Multi-hop Reasoning:
    1. Finds 1-hop and 2-hop neighbors of query entities.
    2. Finds indirect paths (relational bridges) between pairs of query entities.
    3. Filters by document IDs if specified for focused research.
    """
    if not entities:
        return []

    driver = await get_driver()
    async with driver.session() as session:
        # Multi-strategy search:
        # Strategy A: 2-hop Neighborhood (Broad context)
        # Strategy B: Shortest Paths between key entities (Relational Bridge)

        # We use a single query that UNIONs neighborhood and path insights
        query = """
        // 1. & 2. Hop broad context with case-insensitive partial matching
        // Match ANY label (Citizen, GP, District, Operator, Mobile, etc.)
        MATCH (s)
        WHERE (s:Entity OR s:Citizen OR s:GP OR s:District OR s:Block OR s:Scheme OR s:FraudFlag OR s:RationCard OR s:Mobile OR s:Operator)
          AND any(e IN $entities WHERE s.name =~ ("(?i).*" + e + ".*") OR s.id =~ ("(?i).*" + e + ".*") OR s.uid =~ ("(?i).*" + e + ".*") OR s.text =~ ("(?i).*" + e + ".*") OR s.number =~ ("(?i).*" + e + ".*"))
        WITH s
        MATCH (s)-[r1]-(n)-[r2]-(t)
        WHERE (t:Entity OR t:Citizen OR t:GP OR t:District OR t:Block OR t:Scheme OR t:FraudFlag OR t:RationCard OR t:Mobile OR t:Operator)
          AND NOT any(e IN $entities WHERE t.name =~ ("(?i).*" + e + ".*") OR t.id =~ ("(?i).*" + e + ".*") OR t.uid =~ ("(?i).*" + e + ".*"))
        """

        if document_ids:
            query += " AND (any(docId IN $document_ids WHERE docId IN coalesce(s.document_ids, [])) OR any(docId IN $document_ids WHERE docId IN coalesce(t.document_ids, []))) "

        query += """
        WITH s, r1, n, r2, t
        RETURN s.name + " is linked to " + t.name + " through " + n.name + " (Rel: " + type(r1) + " -> " + type(r2) + ")" AS insight
        LIMIT 15
        
        UNION
        
        // 1. Hop direct neighbors with fuzzy matching
        MATCH (s)
        WHERE (s:Entity OR s:Citizen OR s:GP OR s:District OR s:Block OR s:Scheme OR s:FraudFlag OR s:RationCard OR s:Mobile OR s:Operator)
          AND any(e IN $entities WHERE s.name =~ ("(?i).*" + e + ".*") OR s.id =~ ("(?i).*" + e + ".*") OR s.uid =~ ("(?i).*" + e + ".*") OR s.text =~ ("(?i).*" + e + ".*") OR s.number =~ ("(?i).*" + e + ".*"))
        WITH s
        MATCH (s)-[r]-(t)
        WHERE (t:Entity OR t:Citizen OR t:GP OR t:District OR t:Block OR t:Scheme OR t:FraudFlag OR t:RationCard OR t:Mobile OR t:Operator)
          AND NOT any(e IN $entities WHERE t.name =~ ("(?i).*" + e + ".*") OR t.id =~ ("(?i).*" + e + ".*") OR t.uid =~ ("(?i).*" + e + ".*"))
        """

        if document_ids:
            query += " AND (any(docId IN $document_ids WHERE docId IN coalesce(s.document_ids, [])) OR any(docId IN $document_ids WHERE docId IN coalesce(t.document_ids, []))) "

        query += """
        RETURN s.name + " --(" + type(r) + ")--> " + t.name + " (Context: " + coalesce(r.description, "N/A") + ")" AS insight
        LIMIT 15
        """

        try:
            result = await session.run(query, entities=entities, document_ids=document_ids)
            records = await result.data()

            insights = [rec["insight"] for rec in records]
            logger.info(
                f"Graph Multi-hop: Uncovered {len(insights)} relational insights for {entities}"
            )
            return insights

        except Exception as e:
            logger.error(f"Multi-hop Graph Search failed: {e}")
            # Fallback to simple neighbor search
            return await _fallback_neighbor_search(entities, document_ids)


async def _fallback_neighbor_search(
    entities: List[str], document_ids: Optional[List[str]] = None
) -> List[str]:
    """Standard 1-hop fallback."""
    driver = await get_driver()
    async with driver.session() as session:
        query = """
        MATCH (s)-[r]-(t)
        WHERE (s:Citizen OR s:GP OR s:Entity) AND (s.name IN $entities OR s.uid IN $entities)
        """
        if document_ids:
            query += " AND (any(id IN $document_ids WHERE id IN coalesce(s.document_ids, [])) OR any(id IN $document_ids WHERE id IN coalesce(t.document_ids, []))) "
        query += " RETURN coalesce(s.name, s.uid) as s_label, type(r) as rel_type, r.description as description, coalesce(t.name, t.uid, t.id) as t_label LIMIT 15"

        result = await session.run(query, entities=entities, document_ids=document_ids)
        records = await result.data()
        facts = [f"{rec['s_label']} --({rec['rel_type']})--> {rec['t_label']}" for rec in records]
        return facts


async def get_usr_citizen_fraud_snapshot(name: str, limit: int = 5) -> List[Dict[str, Any]]:
    """
    Deterministically resolve USR citizens by name and return fraud-relevant context.

    This is used for direct user questions like:
      "Does Pramila Das come under fraud?"
    to avoid relying only on vector retrieval context windows.
    """
    if not name or not name.strip():
        return []

    driver = await get_driver()
    async with driver.session() as session:
        query = """
        MATCH (c:Citizen)
        WHERE toLower(coalesce(c.name, "")) CONTAINS toLower($name)
        OPTIONAL MATCH (c)-[:RESIDES_IN]->(g:GP)-[:PART_OF]->(b:Block)-[:PART_OF]->(d:District)
        OPTIONAL MATCH (c)-[rel:FLAGGED_AS]->(f:FraudFlag)
        WITH c, g, b, d, rel, f
        ORDER BY coalesce(rel.confidence, 0) DESC
        RETURN
          c.uid AS uid,
          c.name AS name,
          c.dob AS dob,
          c.gender AS gender,
          c.vulnerability_score AS vulnerability_score,
          c.risk_tier AS risk_tier,
          d.name AS district,
          b.name AS block,
          g.name AS gp,
          collect(DISTINCT CASE
            WHEN f IS NULL THEN NULL
            ELSE {
              rule: f.rule,
              type: f.type,
              description: f.description,
              confidence: rel.confidence
            }
          END) AS flags
        LIMIT $limit
        """
        result = await session.run(query, name=name.strip(), limit=limit)
        records = await result.data()

        # Strip null placeholders from collected flags.
        for row in records:
            row["flags"] = [f for f in row.get("flags", []) if f]
        return records


async def get_usr_citizen_name_suggestions(name: str, limit: int = 8) -> List[Dict[str, Any]]:
    """
    Suggest closest citizen name matches from USR graph when exact/contains lookup misses.
    """
    if not name or not name.strip():
        return []

    tokens = [t for t in name.strip().split() if len(t) >= 2]
    if not tokens:
        return []

    token_clauses = " OR ".join(
        [f"toLower(coalesce(c.name, '')) CONTAINS toLower($t{i})" for i in range(len(tokens))]
    )
    params: Dict[str, Any] = {"limit": limit}
    for i, t in enumerate(tokens):
        params[f"t{i}"] = t

    driver = await get_driver()
    async with driver.session() as session:
        query = f"""
        MATCH (c:Citizen)
        WHERE {token_clauses}
        OPTIONAL MATCH (c)-[:RESIDES_IN]->(g:GP)-[:PART_OF]->(b:Block)-[:PART_OF]->(d:District)
        RETURN
          c.uid AS uid,
          c.name AS name,
          d.name AS district,
          b.name AS block,
          g.name AS gp
        LIMIT $limit
        """
        result = await session.run(query, **params)
        return await result.data()


async def get_usr_citizen_fraud_snapshot_by_uid(uid: str) -> Dict[str, Any] | None:
    """
    Deterministically resolve one USR citizen by UID and include linked duplicate evidence.
    """
    if not uid or not uid.strip():
        return None

    driver = await get_driver()
    async with driver.session() as session:
        query = """
        MATCH (c:Citizen {uid: $uid})
        OPTIONAL MATCH (c)-[:RESIDES_IN]->(g:GP)-[:PART_OF]->(b:Block)-[:PART_OF]->(d:District)
        OPTIONAL MATCH (c)-[rel:FLAGGED_AS]->(f:FraudFlag)
        OPTIONAL MATCH (c)-[dup:POTENTIAL_DUPLICATE]-(other:Citizen)
        WITH c, g, b, d,
             collect(DISTINCT CASE
               WHEN f IS NULL THEN NULL
               ELSE {
                 rule: f.rule,
                 type: f.type,
                 description: f.description,
                 confidence: rel.confidence
               }
             END) AS flags,
             collect(DISTINCT CASE
               WHEN other IS NULL THEN NULL
               ELSE {
                 uid: other.uid,
                 name: other.name,
                 confidence: dup.confidence,
                 rule: dup.rule
               }
             END) AS duplicate_links
        RETURN
          c.uid AS uid,
          c.name AS name,
          c.dob AS dob,
          c.gender AS gender,
          c.vulnerability_score AS vulnerability_score,
          c.risk_tier AS risk_tier,
          d.name AS district,
          b.name AS block,
          g.name AS gp,
          flags,
          duplicate_links
        LIMIT 1
        """
        result = await session.run(query, uid=uid.strip())
        row = await result.single()
        if not row:
            return None

        data = dict(row)
        data["flags"] = [f for f in data.get("flags", []) if f]
        data["duplicate_links"] = [x for x in data.get("duplicate_links", []) if x]
        return data


async def delete_document_triplets(document_id: str):
    """
    Removes document association from all nodes and edges.
    If a node or edge has no document associations left, it is deleted.
    """
    driver = await get_driver()
    async with driver.session() as session:
        # 1. Update edges: remove doc_id from list. If empty, delete edge.
        query_edges = """
        MATCH ()-[r:RELATED]-()
        WHERE $document_id IN coalesce(r.document_ids, [])
        SET r.document_ids = [id IN r.document_ids WHERE id <> $document_id]
        WITH r
        WHERE size(r.document_ids) = 0
        DELETE r
        """

        # 2. Update nodes: remove doc_id from list. If empty, delete node.
        query_nodes = """
        MATCH (n:Entity)
        WHERE $document_id IN coalesce(n.document_ids, [])
        SET n.document_ids = [id IN n.document_ids WHERE id <> $document_id]
        WITH n
        WHERE size(n.document_ids) = 0
        DETACH DELETE n
        """

        try:
            await session.run(query_edges, document_id=document_id)
            await session.run(query_nodes, document_id=document_id)
            logger.info(f"Purged Knowledge Graph associations for document {document_id}")
        except Exception as e:
            logger.error(f"Failed to purge Knowledge Graph associations for {document_id}: {e}")
