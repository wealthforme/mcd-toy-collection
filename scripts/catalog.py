# -*- coding: utf-8 -*-
"""构建玩具总库 data/toys.json。

数据来源（全部只读 MCP 调用）：
1. 当前在售：query-nearby-stores -> query-meals -> query-meal-detail(套餐 rounds) -> query-meal-detail(玩具 code 取图)
2. 历史获得：order-list 历史订单里的玩具子项（部分已下市，图片取不到时用占位卡）
3. 周边周边：mall-points-products 中 catName=玩具 / 名称含玩具的积分兑换商品
4. 活动线索：campaign-calendar 中提到玩具的活动
"""
import json, pathlib, sys, time, re

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from mcp_client import McdMcp, guess_image
from scan_toys import find_meal_codes, toys_of_meal, toy_image, guess_series, TOY_KEYWORDS

ROOT = pathlib.Path(__file__).resolve().parent.parent
DATA = ROOT / "data"


def placeholder(name, code):
    """本地生成占位图（SVG data URI），不依赖任何外部图床"""
    txt = (name or "玩具")[:10]
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" width="300" height="300">'
           f'<rect width="300" height="300" fill="#FFC72C"/>'
           f'<circle cx="150" cy="120" r="62" fill="#DA291C"/>'
           f'<text x="150" y="140" font-size="64" text-anchor="middle" fill="#fff" '
           f'font-family="sans-serif">?</text>'
           f'<text x="150" y="228" font-size="20" text-anchor="middle" fill="#5a3d00" '
           f'font-family="sans-serif">{txt}</text></svg>')
    return "data:image/svg+xml;utf8," + svg.replace("#", "%23").replace("<", "%3C").replace(">", "%3E").replace('"', "'")


def main():
    mcp = McdMcp()
    toys = {}

    def put(code, name, image, source, extra=None):
        if not code:
            return False
        key = str(code)
        rec = toys.get(key)
        if rec is None:
            rec = toys[key] = {"code": key, "name": name or "玩具", "image": image or "",
                               "source": source, "stores": [], "status": "", "series": ""}
            new = True
        else:
            new = False
            if source == "current" and rec["source"] != "current":
                rec["source"] = "current"
        if image and not rec["image"]:
            rec["image"] = image
        if extra:
            rec.update({k: v for k, v in extra.items() if v is not None and v != ""})
        if name and rec["name"] in ("", "玩具"):
            rec["name"] = name
        return new

    # ---- 1. 当前在售 ----
    # searchType=1 返回账号关联门店，稳定性最高；跨店覆盖由 scan_toys.py 负责
    d0 = mcp.data("query-nearby-stores", {"beType": 1, "searchType": 1})
    time.sleep(0.15)
    store = None
    if isinstance(d0, list) and d0:
        s = d0[0]
        store = {"storeCode": s.get("storeCode"), "storeName": s.get("storeName"),
                 "address": s.get("address"), "beCode": s.get("beCode")}
    current = []
    if store:
        print(f"门店：{store['storeName']} ({store['storeCode']})")
        for mc in find_meal_codes(mcp, store["storeCode"]):
            time.sleep(0.15)
            for t in toys_of_meal(mcp, store["storeCode"], mc["code"]):
                time.sleep(0.15)
                img = toy_image(mcp, store["storeCode"], t["code"]) or guess_image(t["code"])
                time.sleep(0.15)
                put(t["code"], t["name"], img, "current",
                    {"status": "当前在售", "meal": mc["code"], "mealCat": mc.get("cat"),
                     "round": t.get("round"), "diffPrice": t.get("diffPrice"),
                     "storeName": store["storeName"], "storeCode": store["storeCode"]})
                current.append(str(t["code"]))
        print(f"当前在售玩具 {len(set(current))} 款")

    # ---- 2. 历史订单 ----
    d = mcp.data("order-list", {})
    time.sleep(0.15)

    def walk(node, out):
        """递归展开套餐子项，收集含玩具关键词的条目"""
        if isinstance(node, dict):
            nm = str(node.get("name") or node.get("productName") or "")
            if any(k in nm for k in TOY_KEYWORDS):
                out.append(node)
            for key in ("comboItemList", "subProductList", "productList", "items", "children"):
                walk(node.get(key), out)
        elif isinstance(node, list):
            for x in node:
                walk(x, out)

    hist = 0
    if isinstance(d, dict):
        for o in (d.get("list") or []):
            oid = o.get("orderId")
            otime = o.get("createTime") or o.get("orderTime") or ""
            found = []
            walk(o.get("orderProductList") or o.get("goods") or o.get("productList"), found)
            for it in found:
                nm = str(it.get("name") or it.get("productName") or "")
                code = it.get("productCode") or it.get("code")
                img = guess_image(code) if code else ""
                if code and store and not img:
                    img = toy_image(mcp, store["storeCode"], code)
                    time.sleep(0.15)
                if put(code or f"hist-{hist}", nm, img, "history",
                       {"status": "历史款（已下市）" if not img else "历史款",
                        "orderId": oid, "orderTime": otime}):
                    hist += 1
    print(f"历史订单玩具 {hist} 款")

    # ---- 3. 商城周边 ----
    mall = 0
    for cat in ["2>8", "2", "1>4"]:
        rows = mcp.data("mall-points-products", {"catRuleIds": cat})
        time.sleep(0.15)
        if not isinstance(rows, list):
            continue
        for r in rows:
            nm = str(r.get("spuName") or "")
            # 玩具类目 / 名称含玩具关键词 / 联名周边（如 Nike Book 2 麦当劳特别联名款）均计入收藏册
            istoy = (str(r.get("catName")) == "玩具") or any(k in nm for k in TOY_KEYWORDS) \
                or ("联名" in nm and str(r.get("price")) in ("0", ""))
            if not istoy:
                continue
            if put(r.get("spuId"), nm, r.get("spuImage"), "mall",
                   {"status": "积分兑换", "point": r.get("point"), "price": r.get("price"),
                    "catName": r.get("catName"), "spuId": r.get("spuId"),
                    "selling": r.get("selling"), "upTime": r.get("upTime"),
                    "downTime": r.get("downTime")}):
                mall += 1
    print(f"商城玩具周边 {mall} 款")

    # ---- 4. 活动线索 ----
    _, cal_meta = mcp.call("campaign-calendar", {})
    cal = cal_meta.get("text", "")  # 该工具返回 Markdown，非 JSON
    events = []
    if isinstance(cal, str):
        for blk in re.split(r"\n(?=-   \*\*活动标题\*\*)", cal):
            mt = re.search(r"\*\*活动标题\*\*：(.+)", blk)
            if not mt:
                continue
            title = mt.group(1).strip()
            if any(k in blk for k in TOY_KEYWORDS) or "乐园餐" in blk:
                mi = re.search(r'<img src="([^"]+)"', blk)
                mc = re.search(r"\*\*活动内容介绍\*\*：([\s\S]*?)\n\s*\*\*活动图片介绍\*\*", blk)
                events.append({"title": title, "image": mi.group(1) if mi else "",
                               "desc": re.sub(r"\s+", " ", mc.group(1)).strip() if mc else ""})
    print(f"相关活动 {len(events)} 条")

    # ---- 5. 合并跨城扫描结果：availability.json 里在送的款升级为"当前在售" ----
    avail_path = DATA / "availability.json"
    if avail_path.exists():
        try:
            avail = json.loads(avail_path.read_text(encoding="utf-8"))
        except Exception:
            avail = {}
        promoted = 0
        for at in avail.get("toys") or []:
            code = str(at.get("code") or "")
            if not code or code not in toys:
                continue
            rec = toys[code]
            rec["availableStores"] = len(at.get("stores") or [])
            if rec["source"] != "current":
                # 同一 code 在别的城市门店仍在送：以"当前在售"为主分类，历史来源信息保留在 orderId/orderTime
                rec["source"] = "current"
                rec["status"] = "当前在售"
                promoted += 1
            if not rec.get("image") or not str(rec["image"]).startswith("http"):
                rec["image"] = at.get("image") or rec["image"]
        if promoted:
            print(f"按跨城扫描结果升级为当前在售：{promoted} 款")
        current = [t["code"] for t in toys.values() if t["source"] == "current"]

    for t in toys.values():
        t["series"] = t.get("series") or guess_series(t["name"])
        if not t["image"] and str(t["code"]).isdigit():
            # 官方图床规则兜底：ProductPool/MS_<code>_600.png（已实测多个历史玩具可用）
            t["image"] = guess_image(t["code"])
        if not t["image"]:
            t["image"] = placeholder(t["name"], t["code"])
            t["imageIsPlaceholder"] = True
        else:
            t["imageIsPlaceholder"] = False

    order = {"current": 0, "history": 1, "mall": 2}
    by_src = {"current": 0, "history": 0, "mall": 0}
    for t in toys.values():
        by_src[t["source"]] = by_src.get(t["source"], 0) + 1
    out = {
        "generatedAt": time.strftime("%Y-%m-%d %H:%M:%S"),
        "store": store or {},
        "toys": sorted(toys.values(), key=lambda x: (order.get(x["source"], 9), -len(x.get("stores") or []), x["code"])),
        "events": events,
        "stats": {"total": len(toys), "current": by_src["current"], "history": by_src["history"],
                  "mall": by_src["mall"]},
    }
    DATA.mkdir(parents=True, exist_ok=True)
    (DATA / "toys.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\n总库 {len(toys)} 款 -> {DATA / 'toys.json'}")


if __name__ == "__main__":
    main()
