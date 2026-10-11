# -*- coding: utf-8 -*-
"""探测门店搜索能力：确定能否按经纬度/分页拿到不同城市的门店。"""
import json, pathlib, sys

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from mcp_client import McdMcp

TARGETS = {"query-nearby-stores", "query-party-city", "query-store-detail"}

mcp = McdMcp()
res = mcp.rpc("tools/list", {})
tools = res.get("result", {}).get("tools", [])
out = []
for t in tools:
    if t.get("name") in TARGETS:
        out.append({"name": t["name"], "desc": (t.get("description") or "")[:300],
                    "schema": t.get("inputSchema")})
pathlib.Path(__file__).parent.parent.joinpath("data/tools_schema.json").write_text(
    json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
print(json.dumps(out, ensure_ascii=False, indent=1))
