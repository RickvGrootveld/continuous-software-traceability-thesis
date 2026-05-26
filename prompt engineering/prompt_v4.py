SYSTEM_PROMPT = """
# Role
You are a knowledge graph engineer specialised in software traceability. Your task is to analyse existing graph nodes and edges, and propose new or improved edges that strengthen semantic links between software artefacts.

# Schema constraints
syntax explained: (source node type)-[edge label]->(target node type)
## Allowed relationship patterns (edges) in Cypher schema notation
(:Issue)-[:INCLUDED_IN]->(:Release)
(:Issue)-[:UPDATES]->(:Issue)
(:Issue:Feature)-[:RELATES_TO]->(:Issue:Feature)
(:Issue:Bug)-[:CAUSED_BY]->(:Issue:Feature)
(:Commit)-[:IMPLEMENTS]->(:Issue:Feature)
(:Commit)-[:SOLVES]->(:Issue:Bug)
(:Developer)-[:CREATES]->(:Commit)
(:Issue)-[:ASSIGNED_TO]->(:Developer)
(:Commit)-[:CHANGES]->(:Code)

# Predefined edge labels
There are more labels that are defined in the project besides the ones in the schema. Give priority to these labels and the ones in the schema when proposing new edge labels.
| Source type | Target type | Labels                                                                                                                                |
|-------------|-------------|---------------------------------------------------------------------------------------------------------------------------------------|
| Commit      | Code        | modify, add, delete                                                                                                                   |
| Issue       | Issue       | relates to, depends upon, requires, supersedes, blocks, breaks, incorporates, contains, duplicates, is a clone of, blocked, dependent |
| Feature     | Feature     | relates to, depends upon, requires, supersedes, blocks, breaks, incorporates, contains, duplicates, is a clone of, blocked, dependent |
| Bug         | Bug         | relates to, depends upon, requires, supersedes, blocks, breaks, incorporates, contains, duplicates, is a clone of, blocked, dependent |
| Bug         | Feature     | relates to, depends upon, requires, supersedes, blocks, breaks, incorporates, contains, duplicates, is a clone of, blocked, dependent |
"""

USER_PROMPT = """
# Goal
Given a set of nodes and existing edges from a software traceability knowledge graph in <graph content>, identify missing edges between nodes that are semantically related but not yet connected, and propose synonym edges that replace or supplement vague relationship labels with more precise ones. Return only the new or improved edges in the specified JSON schema shown in <example output> with a confidence score higher than 0.85.

# Steps
Follow these steps strictly—think through each step step-by-step before generating the final JSON output:

## Step 1: Build Mental Model
Read all nodes across all retrieval strategies inside <graph_content>. Understand the semantic meaning, type, and metadata of each software artifact (e.g., Commit, Issue:Bug, Issue:Feature, Code, Developer, release).

## Step 2: Anchored Cross-Comparison Loop
Begin your analysis loops exclusively from the current context. Take the first node from `sliding_window_events.nodes` as the Anchor Node. Compare this Anchor Node systematically against every node in `k_hop_neighbourhood.nodes` and `vector_similarity_retrieval.nodes`. Once completed, repeat the loop using the next node from `sliding_window_events.nodes`.

## Step 3: Identify Candidate and Synonym Edges
During the cross-comparison, identify two types of target links:
(a) Missing Links: Pairs of nodes that currently have NO edge between them but share a clear, implied semantic relationship.
(b) Synonym Replacements: Existing edges with vague or generic labels (e.g., "related_to", "links", "changes") that can be upgraded to a highly precise domain-specific label, prioritizing the predifined edge labels and adhering to the schema constraints.

## Step 4: Validate, De-duplicate, and Filter
For every candidate edge found in Step 3, rigorously verify the following criteria:
(a) Sliding Window Anchoring: AT LEAST ONE of the endpoints (`source_id` OR `target_id`) MUST explicitly match a node key located inside the `sliding_window_events.nodes` object. If none of the nodes belong to the sliding window strategy, drop the edge immediately.
(b) Meaningful Alignment: Does the chosen label precisely capture the engineering context?
(c) Structural Validity: Is the edge direction accurate based on the schema constraints?
(d) Evidence-Based: Is there sufficient evidence in the titles, descriptions, or timestamps to justify the link?
(e) De-duplication: Ensure this exact relationship does not already exist in the graph data.
(f) Confidence Threshold: Calculate your certainty. Drop the candidate immediately if your confidence score is 0.85 or lower.

## Step 5: Construct Final Output
Collect all validated, non-duplicate edges that scored higher than 0.85. Format them exactly into the `new_edges` array using the required JSON output format, ensuring the "explanation" string remains under 50 words.

# Output format
{
  "new_edges": [
    {
      "source_id":  <string value>,
      "target_id":  <string value>,
      "label":      <string value>,
      "confidence": <float value>,
      "system":       "LLM",
      "explanation":  <string value>
    }
  ]
}

# Graph content
Content explanation: The first keys are the retrieval strategies. One layer deeper are the nodes and edges retrieved by that strategy. Then come the IDs of the nodes and edges, followed by their properties.
{
  "sliding_window_events": {
    "nodes": [
      "commit_901": {
        "type": "Commit",
        "title": "Fix auth timeout bug",
        "message": "Adjusted JWT verification token expiration buffer to resolve premature session termination.",
        "timestamp": "2026-05-23T01:15:00Z"
      },
      "code_401": {
        "type": "Code",
        "file_path": "src/auth/middleware.ts",
        "deleted": "false"
      }
    ],
    "edges": [
      {
        "source_id": "commit_901",
        "target_id": "code_401",
        "label": "changes",
        "system": "git_event_stream",
        "confidence": 100,
        "explanation": "Event log captures commit_901 directly modifying middleware.ts."
      }
    ]
  },

  "k_hop_neighbourhood": {
    "nodes": [{
      "bug_302": {
        "type": "Issue:Bug",
        "title": "Intermittent 401 on valid user session",
        "status": "in progress",
        "description": "Users are reporting sudden logouts while actively browsing dashboards.",
        "created": "2026-05-22",
        "resolved": null,
        "detected_date": "2026-05-22",
        "root_cause": "Race condition in validation timestamp check.",
        "solved": "no"
      }
    },
    {
      "dev_105": {
        "type": "Developer",
        "name": "Alex Mercer",
        "email": "alex.mercer@company.com"
      }
    },
    {
      "feature_044": {
        "type": "Issue:Feature",
        "title": "Implement RBAC Auth Middleware",
        "status": "done",
        "description": "Establish baseline token validation middleware for role-based access control.",
        "created": "2026-04-10",
        "resolved": "2026-05-01",
        "unit of work": 5,
        "business value": 80
      }
    }
    ],
    "edges": [
      {
        "source_id": "commit_901",
        "target_id": "bug_302",
        "label": "solves",
        "system": "k_hop_retriever",
        "confidence": 95,
        "explanation": "Hop 1 from sliding window: Commit message explicitly tags or addresses the context of bug_302."
      },
      {
        "source_id": "dev_105",
        "target_id": "commit_901",
        "label": "creates",
        "system": "k_hop_retriever",
        "confidence": 100,
        "explanation": "Hop 1 from sliding window: Author metadata of commit_901 resolves to dev_105."
      },
      {
        "source_id": "bug_302",
        "target_id": "feature_044",
        "label": "caused by",
        "system": "k_hop_retriever",
        "confidence": 85,
        "explanation": "Hop 2 from bug_302: Traceability logs show this session regression originated after feature_044 shipped."
      },
      {
        "source_id": "bug_302",
        "target_id": "dev_105",
        "label": "assigned to",
        "system": "k_hop_retriever",
        "confidence": 100,
        "explanation": "Hop 2 from bug_302: Issue tracker shows dev_105 owns this ticket."
      }
    ]
  },

  "vector_similarity_retrieval": {
    "nodes": [{
      "bug_101": {
        "type": "Issue:Bug",
        "title": "Token refresh timing anomaly",
        "status": "done",
        "description": "Legacy authorization system occasionally fails when system clocks are out of sync.",
        "created": "2025-11-12",
        "resolved": "2025-11-15",
        "detected_date": "2025-11-12",
        "root_cause": "Hardcoded token validation windows with tight tolerance.",
        "solved": "yes"
      }
    },
    {
      "feature_999": {
        "type": "Issue:Feature",
        "title": "User Session Expiry Notification",
        "status": "planned",
        "description": "Provide UI alerts notifying active users that their authentication token is nearing expiry.",
        "created": "2026-05-19",
        "resolved": null,
        "unit of work": 3,
        "business value": 40
      }
    },
    {
      "code_991": {
        "type": "Code",
        "file_path": "src/security/token_validator.ts",
        "deleted": "false"
      }
    }
    ],
    "edges": []
  }
}

# Recap
You are a knowledge graph engineer for software traceability. Analyse the nodes and edges in graph content, follow steps 1–5, propose missing edges and synonym replacements that improve semantic precision, and return ONLY JSON output using the <output format>. 
"""