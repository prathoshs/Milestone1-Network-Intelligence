# phase7/c2_network_operations_assistant.py
import os, json, requests, anthropic
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()
api_key = os.getenv("ANTHROPIC_API_KEY")

BASE = os.getenv("NETWORK_API_BASE", "http://127.0.0.1:8000")
client = anthropic.Anthropic()
MODEL = os.getenv("CLAUDE_MODEL", "claude-sonnet-4-5")

TOOLS = [
 {"name":"get_network_summary","description":"Get current network summary from API1.",
  "input_schema":{"type":"object","properties":{"as_of":{"type":"string"}},"required":["as_of"]}},
 {"name":"get_grid_activity","description":"Get activity for a grid from API2.",
  "input_schema":{"type":"object","properties":{"grid_id":{"type":"string"},"as_of":{"type":"string"}},"required":["grid_id","as_of"]}},
 {"name":"get_hotspots","description":"Get current hotspots from API3.",
  "input_schema":{"type":"object","properties":{"limit":{"type":"integer"},"severity":{"type":"string"},"as_of":{"type":"string"}},"required":["limit","severity","as_of"]}},
 {"name":"get_grid_features","description":"Get ML/network features for a grid from API4.",
  "input_schema":{"type":"object","properties":{"grid_id":{"type":"string"}},"required":["grid_id"]}},
 {"name":"get_anomaly_score","description":"Get anomaly/risk evidence for a grid.",
  "input_schema":{"type":"object","properties":{"grid_id":{"type":"string"},"as_of":{"type":"string"}},"required":["grid_id","as_of"]}},
 {"name":"get_grid_location","description":"Get geographic location for a grid.",
  "input_schema":{"type":"object","properties":{"grid_id":{"type":"string"}},"required":["grid_id"]}},
 {"name":"get_pipeline_status","description":"Check pipeline health and data trustworthiness.",
  "input_schema":{"type":"object","properties":{}}},
]

PATHS = {
 "get_network_summary":"/network/summary",
 "get_grid_activity":"/network/grid/{grid_id}/activity",
 "get_hotspots":"/network/hotspots",
 "get_grid_features":"/network/grid/{grid_id}/features",
 "get_anomaly_score":"/network/grid/{grid_id}/anomaly",
 "get_grid_location":"/network/grid/{grid_id}/location",
 "get_pipeline_status":"/pipeline/status",
}

def call_tool(name, args):
    try:
        path = PATHS[name].format(**args)
        r = requests.get(BASE + path, params={
            k:v for k,v in args.items() if k not in ("grid_id",)
        }, timeout=10)
        r.raise_for_status()
        return {"tool":name, "status":"success", "data":r.json()}
    except Exception as e:
        return {"tool":name, "status":"failed", "error":str(e)}

SYSTEM = """You are the Network Operations Assistant for the Milan grid.
ALWAYS use tools for factual network claims. Never rely on memory.
Before reporting a situation as fact, call get_pipeline_status().
Cite the tool producing every figure or factual network observation.
If a tool fails, report the failure and narrow the conclusion; never estimate.
Activity measures are NOT counts or MB. Do not claim congestion, capacity
failure, or service failure unless directly supported by evidence.
Separate observed evidence, inference, uncertainty, and recommended checks."""

def ask(question):
    messages = [{"role":"user","content":question}]
    evidence = []
    while True:
        response = client.messages.create(
            model=MODEL, max_tokens=1200,
            system=SYSTEM, tools=TOOLS, messages=messages)
        if response.stop_reason != "tool_use":
            return response.content[0].text, evidence
        messages.append({"role":"assistant","content":response.content})
        results = []
        for block in response.content:
            if block.type == "tool_use":
                result = call_tool(block.name, block.input)
                evidence.append(result)
                results.append({"type":"tool_result",
                                "tool_use_id":block.id,
                                "content":json.dumps(result)})
        messages.append({"role":"user","content":results})
if __name__ == "__main__":
    q = input("NOC question: ")
    answer, evidence = ask(q)
    print("\n" + answer)
    print("\n--- TOOL EVIDENCE ---")
    for e in evidence:
        print(f"{e['tool']}: {e['status']}")