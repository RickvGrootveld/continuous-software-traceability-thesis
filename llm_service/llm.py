from dataclasses import dataclass
from typing import Dict, List
import json


@dataclass
class GraphNode:
    type: str
    id: str
    properties: Dict


@dataclass
class GraphEdge:
    source: str
    target: str
    label: str
    properties: Dict


@dataclass
class LLMEdge:
    source: str
    target: str
    label: str
    properties: Dict

SYSTEM_PROMPT = """
You are an expert software traceability graph enrichment system.

Your task:
- infer missing relationships
- only infer meaningful software engineering relationships
- avoid hallucinations
- use evidence from graph structure and semantics

Allowed relationship labels:
- BLOCKED_BY
- DEPENDS_ON
- RELATED_TO
- CAUSES
- AFFECTS

Return ONLY valid JSON.
"""



def build_prompt(nodes, edges):
    return f"""
Infer missing relationships in this software traceability graph.

NODES:
{json.dumps(nodes, indent=2)}

EDGES:
{json.dumps(edges, indent=2)}

Return JSON ONLY in this format:

[
    {{
        "source": "...",
        "target": "...",
        "label": "BLOCKED_BY",
        "confidence": 0.91,
        "explanation": "short explanation"
    }}
]
"""