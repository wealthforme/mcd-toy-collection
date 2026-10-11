# -*- coding: utf-8 -*-
"""麦当劳 MCP 客户端封装。

Token 读取优先级：
1) 环境变量 MCD_MCP_TOKEN（推荐，符合参赛信息安全声明）
2) 环境变量 MCD_MCP_TOKEN_FILE 指向的文件
3) 本地 ~/.workbuddy/mcp.json 中 mcd-mcp 的 Authorization（仅本机开发方便）
"""
import json, os, re, ssl, pathlib, urllib.request

MCP_URL = os.environ.get("MCD_MCP_URL", "https://mcp.mcd.cn")
DEFAULT_CFG = pathlib.Path.home() / ".workbuddy" / "mcp.json"


def load_token():
    t = os.environ.get("MCD_MCP_TOKEN")
    if t:
        return t.strip()
    f = os.environ.get("MCD_MCP_TOKEN_FILE")
    if f and pathlib.Path(f).exists():
        return pathlib.Path(f).read_text(encoding="utf-8").strip()
    if DEFAULT_CFG.exists():
        cfg = json.loads(DEFAULT_CFG.read_text(encoding="utf-8"))
        node = (cfg.get("mcpServers") or {}).get("mcd-mcp") or {}
        auth = (node.get("headers") or {}).get("Authorization", "")
        if auth.lower().startswith("bearer "):
            return auth[7:].strip()
    raise RuntimeError("未找到 MCP Token，请设置环境变量 MCD_MCP_TOKEN")


def guess_image(code):
    """按麦当劳官方图床规则猜测商品图，HEAD 校验通过后返回 URL，否则空串。

    规则：https://menu-img.mcd.cn/pcm/prod/menu/ProductPool/product/MS_<code>_600.png
    实测当前款与已下市历史款均返回 200，可用于补全订单里取不到图的玩具。
    """
    if not code:
        return ""
    url = f"https://menu-img.mcd.cn/pcm/prod/menu/ProductPool/product/MS_{code}_600.png"
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    try:
        req = urllib.request.Request(url, method="HEAD", headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=15, context=ctx) as r:
            return url if r.status == 200 else ""
    except Exception:
        return ""


class McdMcp:
    def __init__(self, token=None, timeout=60):
        self.token = token or load_token()
        self.timeout = timeout
        self._id = 0
        self._ctx = ssl.create_default_context()
        self._ctx.check_hostname = False
        self._ctx.verify_mode = ssl.CERT_NONE

    def rpc(self, method, params):
        self._id += 1
        body = json.dumps({"jsonrpc": "2.0", "id": self._id, "method": method, "params": params}).encode()
        req = urllib.request.Request(MCP_URL, data=body, method="POST", headers={
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "Authorization": "Bearer " + self.token,
        })
        with urllib.request.urlopen(req, timeout=self.timeout, context=self._ctx) as r:
            return json.loads(r.read().decode("utf-8"))

    def call(self, name, arguments=None):
        """返回 (data, meta)；meta 含业务层 success/code/message"""
        res = self.rpc("tools/call", {"name": name, "arguments": arguments or {}})
        text = "".join(c.get("text", "") for c in (res.get("result", {}) or {}).get("content", [])
                       if c.get("type") == "text")
        meta = {"ok": "error" not in res, "text": text}
        m = re.search(r'"success":(true|false)', text)
        meta["success"] = m.group(1) if m else None
        m = re.search(r'"code":(\d+)', text)
        meta["code"] = m.group(1) if m else ""
        m = re.search(r'"message":"([^"]*)"', text)
        meta["message"] = m.group(1) if m else ""
        return parse_data(text), meta

    def data(self, name, arguments=None):
        """仅返回业务成功时的 data，否则 None"""
        d, meta = self.call(name, arguments)
        if meta["success"] == "false":
            return None
        return d


def parse_data(text):
    """从 MCP 返回文本中提取 data 字段。返回可能是 dict / list / str"""
    seg = text.split("## Original Response")[-1] if "## Original Response" in text else text
    m = re.search(r"\{[\s\S]*\}", seg)
    if not m:
        return None
    try:
        return json.loads(m.group(0)).get("data")
    except Exception:
        return None
