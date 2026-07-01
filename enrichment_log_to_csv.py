import re
import csv

input_path = "results_v2/scalability validation/run_10000_qwen/enrichment.log"
output_file = "results_v2/scalability validation/run_10000_qwen/enrichment_log.csv"

# Define the columns exactly as requested
fields = [
    "window_nodes", "window_edges", "vector_nodes", 
    "neighbourhood_nodes", "neighbourhood_edges", 
    "HTTP_response", "generation_time", "prompt_tokens", 
    "output_tokens", "stop_reason", "valid_edges"
]

records = []
current_record = {field: "-1" for field in fields}
inside_enrichment = False

# Regex patterns to match the log lines
patterns = {
    "window_nodes": re.compile(r"window nodes:\s*(\d+)"),
    "window_edges": re.compile(r"window edges:\s*(\d+)"),
    "vector_nodes": re.compile(r"vector nodes:\s*(\d+)"),
    "neighbourhood_nodes": re.compile(r"neighbourhood nodes:\s*(\d+)"),
    "neighbourhood_edges": re.compile(r"neighbourhood edges\s*(\d+)"),
    "HTTP_response": re.compile(r'HTTP Request:.*"(HTTP/\d+\.\d+\s+[^"]+)"'),
    "generation_time": re.compile(r"response generation time.*:\s*([\d\.]+)"),
    "prompt_tokens": re.compile(r"prompt tokens:\s*(\d+)"),
    "output_tokens": re.compile(r"eval count \(output tokens\):\s*(\d+)"),
    "stop_reason": re.compile(r"stop reason:\s*(\w+)"),
    "valid_edges": re.compile(r"Valid edges extracted length:\s*(\d+)")
}

with open(input_path, "r", encoding="utf-8") as f:
    for line in f:
        if "adding to window" in line and not inside_enrichment:
            inside_enrichment = True
            current_record = {field: "-1" for field in fields}
        
        if inside_enrichment:
            # Check for any of our target metrics in the current line
            for field, pattern in patterns.items():
                match = pattern.search(line)
                if match:
                    current_record[field] = match.group(1)
            
            # Close the record block when the ready signal is published
            if "Published 'ready' signal to knowledge graph service" in line:
                records.append(current_record)
                inside_enrichment = False

# Output to CSV
with open(output_file, "w", newline="", encoding="utf-8") as f:
    writer = csv.DictWriter(f, fieldnames=fields)
    writer.writeheader()
    writer.writerows(records)

print(f"Successfully processed {len(records)} enrichment loops into the output file.")