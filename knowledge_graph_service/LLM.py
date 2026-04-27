import datetime


timestamp = datetime.now().isoformat()

CONFIDENCE_THRESHOLD = 0.8

llm_edge = {
    "source": f"Commit:{commit_hash}",
    "target": f"Code:{cc['file_path']}",
    "label": cc["change_type"],
    "properties": {
        "timestamp": timestamp,
        "system": "LLM",
        "confidence": 0.85,
        "explanation": ""
    }
}