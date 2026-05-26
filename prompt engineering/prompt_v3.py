BETTER_PROMPT = """
# Role
You are a knowledge graph engineer specialised in software traceability. Your task is to analyse existing graph nodes and edges and propose new or improved edges that strengthen semantic links between software artefacts.

# Goal
Given a set of nodes and existing edges from a software traceability knowledge graph, identify missing edges between nodes that are semantically related but not yet connected, and propose synonym edges that replace or supplement vague relationship labels with more precise ones. Return only the new or improved edges in the specified JSON schema with a confidence score higher than 0.85.

# Steps
Follow these steps — think through each before writing output: 
<step id="1"> 
Read all nodes inside <graph_content> and build a mental model of what each artefact represents (requirement, test, code module, bug, etc.). 
</step> 
<step id="2"> 
Inspect the existing edges. Identify: (a) pairs of nodes with NO edge that share an implied semantic relationship, (b) edges whose label is ambiguous or generic (e.g. "related_to", "links") and could be replaced with a domain-specific synonym. 
</step>
 <step id="3"> 
For every candidate edge, ask yourself: (a) Does this relationship add traceability value (e.g. satisfies, implements, validates, depends_on, derived_from, refines)? (b) Is the direction of the edge correct? (c) Is there enough evidence in the node metadata to justify the edge? Only proceed with this edge if your confidence is higher than 0.85. 
</step> 
<step id="4"> 
Compose the output. For each new or improved edge, fill every field of the JSON schema. Add your confidence of adding that relationship and a short "explanation" string (max 20 words) that explains why that edge was created. 
</step>

# Example output
{
  "new_edges": [
    {
      "source_id":  " Commit-017",
      "target_id":  " Feature-042",
      "label":      "Implements ",
      "confidence": 0.91,
      "system":       "LLM",
      "explanation":  "Commit 17 implemented the exact API operations specified in feature 42. Since both have a created date without much time in between, the commit and feature seem to be created for the same purpose but were not linked."
    },
    {
      "source_id":  "Commit-008",
      "target_id":  "File-042",
      "label":      "Renames",
      "confidence": 0.96,
      "system":       "LLM",
      "explanation":  "Commit 8 renames the file rather than changing it. Since the word renaming is more descriptive than changing, I used the word ‘renaming’ as synonym label for this edge.”
."
    }
  ]
}

# Predefined edge labels
| Source type | Target type | Labels                                                                                                                                |
|-------------|-------------|---------------------------------------------------------------------------------------------------------------------------------------|
| Commit      | Code        | modify, add, delete                                                                                                                   |
| Issue       | Issue       | relates to, depends upon, requires, supersedes, blocks, breaks, incorporates, contains, duplicates, is a clone of, blocked, dependent |
| Feature     | Feature     | relates to, depends upon, requires, supersedes, blocks, breaks, incorporates, contains, duplicates, is a clone of, blocked, dependent |
| Bug         | Bug         | relates to, depends upon, requires, supersedes, blocks, breaks, incorporates, contains, duplicates, is a clone of, blocked, dependent |
| Bug         | Feature     | relates to, depends upon, requires, supersedes, blocks, breaks, incorporates, contains, duplicates, is a clone of, blocked, dependent |

# Schema constraints
{
  "nodes": {
    "Release": {
      "version": { "type": "string" }
    },
    "Issue": {
      "title": { "type": "string" },
      "type": { "type": "string" },
      "status": { "type": "string"},
      "description": { "type": "string" },
      "created": { "type": "date" },
      "resolved": { "type": "date" }
    },
    "Issue:Feature": {
      "unit of work": { "type": "integer" },
      "business value": { "type": "integer" }
    },
    "Issue:Bug": {
      "detected_date": { "type": "date" },
      "root_cause": { "type": "string" },
      "solved": { "type": "string"}
    },
    "Commit": {
      "title": { "type": "string" },
      "message": { "type": "string" },
      "timestamp": { "type": "string" }
    },
    "Developer": {
      "name": { "type": "string" },
      "email": { "type": "string" }
    },
    "Code": {
      "file_path": { "type": "string" },
      "deleted": { "type": "string" }
    }
  },
  "edges": {
    "issue_included_in_release": {
      "source_id": "Issue",
      "target_id": "Release",
      "label": "included in"
    },
    "issue_updates_issue": {
      "source_id": "Issue",
      "target_id": "Issue",
      "label": "updates"
    },
    "feature_inherits_issue": {
      "source_id": "Feature",
      "target_id": "Issue",
      "label": "is a"
    },
    "bug_inherits_issue": {
      "source_id": "Bug",
      "target_id": "Issue",
      "label": "is a"
    },
    "feature_relates_to_feature": {
      "source_id": "Feature",
      "target_id": "Feature",
      "label": "relates to"
    },
    "bug_caused_by_feature": {
      "source_id": "Bug",
      "target_id": "Feature",
      "label": "caused by"
    },
    "commit_implements_feature": {
      "source_id": "Commit",
      "target_id": "Feature",
      "label": "implements"
    },
    "commit_solves_bug": {
      "source_id": "Commit",
      "target_id": "Bug",
      "label": "solves"
    },
    "developer_creates_commit": {
      "source_id": "Developer",
      "target_id": "Commit",
      "label": "creates"
    },
    "issue_assigned_to_developer": {
      "source_id": "Issue",
      "target_id": "Developer",
      "label": "assigned to"
    },
    "commit_changes_code": {
      "source_id": "Commit",
      "target_id": "Code",
      "label": "changes"
    }
  }
}

# Graph content
{
  "sliding_window_events": {
    "nodes": {
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
    },
    "edges": {
      "edge_e1": {
        "source_id": "commit_901",
        "target_id": "code_401",
        "label": "changes",
        "system": "git_event_stream",
        "confidence": 100,
        "explanation": "Event log captures commit_901 directly modifying middleware.ts."
      }
    }
  },

  "k_hop_neighbourhood": {
    "nodes": {
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
      },
      "dev_105": {
        "type": "Developer",
        "name": "Alex Mercer",
        "email": "alex.mercer@company.com"
      },
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
    },
    "edges": {
      "edge_k1": {
        "source_id": "commit_901",
        "target_id": "bug_302",
        "label": "solves",
        "system": "k_hop_retriever",
        "confidence": 95,
        "explanation": "Hop 1 from sliding window: Commit message explicitly tags or addresses the context of bug_302."
      },
      "edge_k2": {
        "source_id": "dev_105",
        "target_id": "commit_901",
        "label": "creates",
        "system": "k_hop_retriever",
        "confidence": 100,
        "explanation": "Hop 1 from sliding window: Author metadata of commit_901 resolves to dev_105."
      },
      "edge_k3": {
        "source_id": "bug_302",
        "target_id": "feature_044",
        "label": "caused by",
        "system": "k_hop_retriever",
        "confidence": 85,
        "explanation": "Hop 2 from bug_302: Traceability logs show this session regression originated after feature_044 shipped."
      },
      "edge_k4": {
        "source_id": "bug_302",
        "target_id": "dev_105",
        "label": "assigned to",
        "system": "k_hop_retriever",
        "confidence": 100,
        "explanation": "Hop 2 from bug_302: Issue tracker shows dev_105 owns this ticket."
      }
    }
  },

  "vector_similarity_retrieval": {
    "nodes": {
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
      },
      "feature_999": {
        "type": "Issue:Feature",
        "title": "User Session Expiry Notification",
        "status": "planned",
        "description": "Provide UI alerts notifying active users that their authentication token is nearing expiry.",
        "created": "2026-05-19",
        "resolved": null,
        "unit of work": 3,
        "business value": 40
      },
      "code_991": {
        "type": "Code",
        "file_path": "src/security/token_validator.ts",
        "deleted": "false"
      }
    },
    "edges": {}
  }
}

# Recap
So, you are a knowledge graph engineer for software traceability. Analyse the nodes and edges in graph content, follow steps 1–4, and return ONLY a JSON object adhering the schema above. Propose missing edges and synonym replacements that improve semantic precision. 
"""

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

## Step 2: Cross-Strategy Node Comparison
Systematically compare every individual node inside the `sliding_window_events` block in <graph_content> against every single node found in the other retrieval blocks (`k_hop_neighbourhood` and `vector_similarity_retrieval`). For each pair, evaluate if a relationship exists.

## Step 3: Identify Candidate and Synonym Edges
During the cross-comparison, identify two types of target links:
(a) Missing Links: Pairs of nodes that currently have NO edge between them but share a clear, implied semantic relationship.
(b) Synonym Replacements: Existing edges with vague or generic labels (e.g., "related_to", "links", "changes") that can be upgraded to a highly precise domain-specific label, prioritizing the predifined edge labels and adhering to the schema constraints.

## Step 4: Validate, De-duplicate, and Filter
For every candidate edge found in Step 3, rigorously verify the following criteria:
(a) Sliding Window Anchoring: AT LEAST ONE of the endpoints (`source_id` OR `target_id`) MUST explicitly match a node key located inside the `sliding_window_events.nodes` object. If both nodes belong exclusively to background retrieval strategies, drop the edge immediately.
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