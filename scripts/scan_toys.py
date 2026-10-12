# -*- coding: utf-8 -*-
"""扫描开心乐园餐当前赠送的玩具（含官方图片）。

链路（全部只读）：
  query-nearby-stores(city)      -> 城市代表门店
  query-meals(storeCode)         -> 菜单，定位"开心乐园"分类 / tags 含"开心乐园餐"
  query-meal-detail(乐园餐 code) -> rounds 中名称含"玩具"的选配轮 -> 玩具 code/name
  query-meal-detail(玩具 code)   -> 玩具官方图片 image

用法：
  python scan_toys.py                      # 扫描默认城市列表
  python scan_toys.py --cities 深圳,上海    # 指定城市
  python scan_toys.py --all-cities         # 用 query-party-city 拉取全部城市（调用量大）
  python scan_toys.py --limit 10           # 最多扫描 10 个城市
"""
import argparse, json, pathlib, ssl, sys, time, urllib.request

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from mcp_client import McdMcp, guess_image

ROOT = pathlib.Path(__file__).resolve().parent.parent
DATA = ROOT / "data"

# MCP 门店检索只支持「城市 + 关键词」双条件；关键词用行政区名可扩大召回
CITY_KEYWORDS = {
    "深圳市": ["麦当劳", "南山", "福田", "罗湖", "宝安", "龙华", "龙岗", "光明", "坪山", "盐田"],
    "上海市": ["麦当劳", "浦东", "徐汇", "静安", "黄浦", "长宁", "闵行", "杨浦"],
    "北京市": ["麦当劳", "朝阳", "海淀", "东城", "西城", "丰台", "通州", "大兴"],
    "广州市": ["麦当劳", "天河", "越秀", "海珠", "番禺", "白云", "荔湾"],
    "成都市": ["麦当劳", "武侯", "锦江", "高新", "青羊", "成华", "金牛"],
    "杭州市": ["麦当劳", "西湖", "拱墅", "滨江", "余杭", "上城"],
}
DEFAULT_CITIES = list(CITY_KEYWORDS.keys())  # 深圳市/上海市/北京市/广州市/成都市/杭州市

TOY_KEYWORDS = ("玩具", "公仔", "摆件", "盲盒", "拼装", "水壶", "背包", "周边")
MEAL_KEYWORDS = ("开心乐园", "乐园餐")


def merge_store_scan(data_dir, store_code, found_toys):
    """把单门店扫描结果合并进 availability.json（门店按 code 覆盖，玩具按 code 合并）。

    保持与全量城市扫描相同的输出结构，页面/CLI 只需读一个文件。
    """
    path = data_dir / "availability.json"
    doc = {"toys": [], "stores": []}
    if path.exists():
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            doc = {"toys": [], "stores": []}

    store_rec = next((s for s in doc.get("stores", [])
                      if str(s.get("storeCode")) == str(store_code)), None)
    if store_rec is None:
        store_rec = {"storeCode": store_code, "city": "", "open": True, "toys": []}
        doc.setdefault("stores", []).append(store_rec)
    store_rec["open"] = True
    store_rec["toys"] = [{"code": c, "name": t["name"]} for c, t in found_toys.items()]

    by_code = {str(t["code"]): t for t in doc.get("toys", [])}
    for c, t in found_toys.items():
        rec = by_code.setdefault(str(c), {"code": str(c), "name": t["name"], "image": "",
                                          "series": guess_series(t["name"]), "stores": [],
                                          "round": t.get("round"), "diffPrice": t.get("diffPrice")})
        rec["image"] = rec.get("image") or t.get("image") or guess_image(c)
        if not any(str(s.get("storeCode")) == str(store_code) for s in rec["stores"]):
            rec["stores"].append({"storeCode": store_code, "storeName": "", "city": "",
                                  "address": ""})
    for t in by_code.values():
        t["storeCount"] = len(t["stores"])
    doc["toys"] = sorted(by_code.values(), key=lambda x: (-x["storeCount"], str(x["code"])))
    doc["scannedAt"] = time.strftime("%Y-%m-%d %H:%M:%S")
    doc["storeCount"] = len(doc.get("stores", []))
    doc["openStoreCount"] = sum(1 for s in doc.get("stores", []) if s.get("open"))
    doc["toyCount"] = len(doc["toys"])
    data_dir.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")


def get_stores(mcp, city, keywords, limit=8):
    """返回去重后的门店列表（不含营业状态）。"""
    seen = {}
    for kw in keywords:
        d = mcp.data("query-nearby-stores", {"beType": 1, "searchType": 2,
                                             "city": city, "keyword": kw})
        if isinstance(d, list):
            for s in d:
                code = s.get("storeCode")
                if code and code not in seen:
                    seen[code] = {"storeCode": code, "storeName": s.get("storeName"),
                                  "address": s.get("address"), "beCode": s.get("beCode"),
                                  "hitKeyword": kw}
        if len(seen) >= limit:
            break
    return list(seen.values())[:limit]


def find_meal_codes(mcp, store_code):
    """返回该门店开心乐园餐的 code 列表"""
    d = mcp.data("query-meals", {"storeCode": store_code, "orderType": 1, "beType": 1})
    if not isinstance(d, dict):
        return []
    cats = d.get("categories") or []
    codes = []
    for c in cats:
        cname = str(c.get("name") or "")
        for m in (c.get("meals") or []):
            tags = "".join(str(t) for t in (m.get("tags") or []))
            hit = any(k in cname for k in MEAL_KEYWORDS) or any(k in tags for k in MEAL_KEYWORDS)
            if hit and m.get("code"):
                codes.append({"code": m["code"], "cat": cname, "tags": m.get("tags")})
    return codes


def toys_of_meal(mcp, store_code, meal_code):
    """从套餐 rounds 中提取玩具项"""
    d = mcp.data("query-meal-detail", {"storeCode": store_code, "orderType": 1, "beType": 1, "code": meal_code})
    if not isinstance(d, dict):
        return []
    out = []
    for r in (d.get("rounds") or []):
        rname = str(r.get("name") or "")
        if not any(k in rname for k in TOY_KEYWORDS) and "玩具" not in rname:
            continue
        for ch in (r.get("choices") or []):
            out.append({"code": ch.get("code"), "name": ch.get("name"),
                        "round": rname, "isDefault": ch.get("isDefault"),
                        "diffPrice": ch.get("diffPrice")})
    return out


def toy_image(mcp, store_code, toy_code):
    d = mcp.data("query-meal-detail", {"storeCode": store_code, "orderType": 1, "beType": 1, "code": toy_code})
    if isinstance(d, dict):
        return d.get("image") or ""
    return ""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cities", default="", help="逗号分隔的城市名")
    ap.add_argument("--limit", type=int, default=0, help="最多扫描城市数（0=不限）")
    ap.add_argument("--all-cities", action="store_true", help="从 query-party-city 拉取全部城市名")
    ap.add_argument("--stores", default="", help="直接指定门店 code，逗号分隔（跨店比价用）")
    ap.add_argument("--per-city", type=int, default=3, help="每城市最多扫描门店数")
    ap.add_argument("--sleep", type=float, default=0.15)
    args = ap.parse_args()

    mcp = McdMcp()

    # 直接指定门店模式：精准比对，结果合并进 availability.json（与全量模式同构）
    if args.stores:
        codes = [c.strip() for c in args.stores.split(",") if c.strip()]
        for sc in codes:
            meal_codes = find_meal_codes(mcp, sc)
            time.sleep(args.sleep)
            found = {}
            for mc in meal_codes:
                for t in toys_of_meal(mcp, sc, mc["code"]):
                    time.sleep(args.sleep)
                    if not t.get("code"):
                        continue
                    t["meal"] = mc["code"]
                    t["image"] = toy_image(mcp, sc, t["code"]) or guess_image(t["code"])
                    time.sleep(args.sleep)
                    found[str(t["code"])] = t
            print(f"{sc}: 乐园餐 {len(meal_codes)} 个 | 玩具 " +
                  "、".join(t["name"] for t in found.values()))
            merge_store_scan(DATA, sc, found)
        print(f"\n完成 {len(codes)} 家门店，已合并写入 {DATA / 'availability.json'}")
        return

    cities = [c.strip() for c in args.cities.split(",") if c.strip()] or list(DEFAULT_CITIES)

    if args.all_cities:
        d = mcp.data("query-party-city", {"spuId": 1830})
        if isinstance(d, list):
            cities = [c.get("name") for c in d if c.get("name")]
            print(f"从 MCP 取到 {len(cities)} 个城市")
    if args.limit:
        cities = cities[:args.limit]

    toys = {}
    stores = []
    miss = []
    for i, city in enumerate(cities, 1):
        kws = CITY_KEYWORDS.get(city) or [city, city.replace("市", ""), "麦当劳"]
        if city not in CITY_KEYWORDS and not city.endswith("市"):
            city_with_suffix = city + "市"
            kws = CITY_KEYWORDS.get(city_with_suffix, [city, "麦当劳"])
            city_query = city_with_suffix
        else:
            city_query = city
        candidates = get_stores(mcp, city_query, kws, args.per_city)
        time.sleep(args.sleep)
        if not candidates:
            miss.append({"city": city, "reason": "未检索到门店"})
            print(f"[{i}/{len(cities)}] {city}: 无门店")
            continue
        opened = []
        for st in candidates:
            st["city"] = city
            probe, pmeta = mcp.call("query-meals", {"storeCode": st["storeCode"],
                                                    "orderType": 1, "beType": 1})
            time.sleep(args.sleep)
            if pmeta["success"] != "true" or not isinstance(probe, dict):
                st["reason"] = f'{pmeta["code"]} {pmeta["message"]}'
                stores.append({**st, "toys": [], "mealCount": 0, "open": False})
                continue
            st["open"] = True
            codes = find_meal_codes(mcp, st["storeCode"])
            time.sleep(args.sleep)
            dedup = {}
            for mc in codes:
                for t in toys_of_meal(mcp, st["storeCode"], mc["code"]):
                    time.sleep(args.sleep)
                    if not t.get("code"):
                        continue
                    dedup.setdefault(t["code"], t)
                    rec = toys.setdefault(t["code"], {
                        "code": t["code"], "name": t["name"], "image": "", "series": "",
                        "round": t.get("round"), "diffPrice": t.get("diffPrice"),
                        "meal": mc["code"], "stores": []})
                    if not any(x["storeCode"] == st["storeCode"] for x in rec["stores"]):
                        rec["stores"].append({"city": city, "storeCode": st["storeCode"],
                                              "storeName": st["storeName"], "address": st.get("address")})
            found = list(dedup.values())
            st["toys"] = [{"code": t["code"], "name": t["name"]} for t in found]
            st["mealCount"] = len(codes)
            stores.append(st)
            opened.append(st)
        open_count = sum(1 for s in stores if s.get("city") == city and s.get("open"))
        print(f"[{i}/{len(cities)}] {city}: 门店 {len(candidates)} 家 / 营业中 {open_count} 家" +
              (" | " + "、".join(f"{s['storeName']}({len(s['toys'])})" for s in opened) if opened else ""))

    for t in toys.values():
        t["storeCount"] = len(t["stores"])
        t["series"] = guess_series(t["name"])
        if not t["image"]:
            t["image"] = guess_image(t["code"])
            if not t["image"]:  # 兜底：向已扫描门店询问单品详情
                for s in stores:
                    t["image"] = toy_image(mcp, s["storeCode"], t["code"])
                    time.sleep(args.sleep)
                    if t["image"]:
                        break
        t["imageIsPlaceholder"] = not str(t["image"]).startswith("http")

    DATA.mkdir(parents=True, exist_ok=True)
    open_stores = [s for s in stores if s.get("open")]
    out = {"scannedAt": time.strftime("%Y-%m-%d %H:%M:%S"),
           "params": {"perCity": args.per_city},
           "cityCount": len(cities), "storeCount": len(stores),
           "openStoreCount": len(open_stores), "toyCount": len(toys),
           "toys": sorted(toys.values(), key=lambda x: (-x["storeCount"], x["code"])),
           "stores": stores, "missed": miss}
    (DATA / "availability.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\n完成：{len(cities)} 城 / {len(stores)} 家门店 / {len(toys)} 款玩具 -> {DATA / 'availability.json'}")




SERIES_NOISE = ("开心乐园", "麦当劳", "特别联名款", "定制", "系列玩具", "玩具", "礼盒",
                "套装", "1个", "随机", "限定")


def guess_series(name):
    """从玩具名提取系列/IP 名。

    「开心乐园小马宝莉&变形金刚系列玩具」→「小马宝莉&变形金刚」；
    「樱桃小丸子定制玩具」→「樱桃小丸子」；「Nike Book 2 麦当劳特别联名款」→「Nike Book 2」。
    提不出有效信息时返回空串（由上层决定是否展示），不再一律标「常规/随机玩具」。
    """
    n = str(name or "").strip()
    if not n:
        return ""
    for sep in ("×", "x", "X", "＊", "&", "和"):
        if sep in n:
            n = n.replace("＆", "&")
            break
    changed = True
    while changed:
        changed = False
        for noise in SERIES_NOISE:
            if noise in n:
                n = n.replace(noise, " ").strip()
                changed = True
    n = " ".join(n.split()).strip(" ·|-—")
    return n if len(n) >= 2 else ""


if __name__ == "__main__":
    main()
