# -*- coding: utf-8 -*-
"""生成单文件玩具站 web/index.html（热门精选 / 电子收藏册 / 找玩具）。

数据来源：data/toys.json（总库）+ data/availability.json（跨城门店可得性）
        + data/collection.json（点亮状态，单品级）
两张表都由 scripts/*.py 通过麦当劳 MCP Server 只读接口拉取，不写死任何业务数据。

点亮模型：开心乐园餐赠品是"一整套系列里的随机一个"，所以
  - 系列款（isSeries）展开成 lineupCount 个单品槽位，逐款点亮；
  - 非系列单品（积分周边等）整体点亮。
"""
import json, pathlib, html

ROOT = pathlib.Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
WEB = ROOT / "web"
E = html.escape

toys_doc = json.loads((DATA / "toys.json").read_text(encoding="utf-8"))
avail_doc = json.loads((DATA / "availability.json").read_text(encoding="utf-8")) \
    if (DATA / "availability.json").exists() else {}
coll_doc = json.loads((DATA / "collection.json").read_text(encoding="utf-8")) \
    if (DATA / "collection.json").exists() else {"version": 2, "slots": {}, "single": {}}
if coll_doc.get("version") != 2:  # 兼容 v1：旧记录视为系列第 1 款
    coll_doc = {"version": 2,
                "slots": {str(c): [{"slot": 1, "name": (i or {}).get("note", ""), "got": True,
                                    "at": (i or {}).get("at", ""), "store": (i or {}).get("store", "")}]
                          for c, i in (coll_doc.get("collected") or {}).items()},
                "single": {}}

ALL = toys_doc.get("toys", [])
SLOTS = coll_doc.get("slots") or {}
SINGLE = coll_doc.get("single") or {}
# 按官方系列图点数预置单品槽位（未命名），保证一整套都能在册、逐款点亮
_padded = False
for _t in ALL:
    if not _t.get("isSeries"):
        continue
    _arr = SLOTS.setdefault(str(_t["code"]), [])
    while len(_arr) < int(_t.get("lineupCount") or 0):
        _arr.append({"slot": len(_arr) + 1, "name": "", "got": False, "at": "", "store": ""})
        _padded = True
if _padded:  # 回写，保证 CLI 与页面看到同一份槽位
    coll_doc["slots"] = SLOTS
    (DATA / "collection.json").write_text(
        json.dumps(coll_doc, ensure_ascii=False, indent=1), encoding="utf-8")
# 门店可用性按玩具 code 汇总，供前端展示"哪些店有"（键统一转 str，防类型漂移）
AVAIL_BY_TOY = {str(t["code"]): t for t in avail_doc.get("toys", [])}
INIT_JSON = json.dumps({"slots": SLOTS, "single": SINGLE}, ensure_ascii=False).replace("</", "<\\/")


def meta_line(t):
    bits = []
    name = t.get("name") or ""
    for key, suffix in (("status", ""), ("round", ""), ("point", " 积分"),
                        ("storeName", ""), ("series", "")):
        v = t.get(key)
        if not v:
            continue
        # series 与名称重复时不再展示（如「海绵宝宝×航海王系列玩具」的 series 同名）
        if key == "series" and (v in name or name in v):
            continue
        bits.append(f"{v}{suffix}")
    if str(t.get("diffPrice") or "").strip() not in ("", "+ ¥0", "+¥0", "0", "None"):
        bits.append(f"差价 {t['diffPrice']}")
    if t.get("price") and str(t["price"]) not in ("0", ""):
        bits.append(f"¥{t['price']}")
    if t.get("orderTime"):
        bits.append(f"{str(t['orderTime'])[:10]} 订单获得")
    if t.get("downTime"):
        bits.append(f"兑换至 {str(t['downTime'])[:10]}")
    if t.get("selling"):
        bits.append(str(t["selling"])[:64])
    return " · ".join(bits)


def avail_badge(t):
    av = AVAIL_BY_TOY.get(str(t["code"]), {})
    n = len(av.get("stores") or [])
    return f'<span class="badge b-avail">{n} 家门店在送</span>' if n else ""


def img_of(t):
    return t.get("image") or ""


# ---------- 单品卡（积分周边等非系列款） ----------
def single_card(t):
    code = str(t["code"])
    got = bool(SINGLE.get(code, {}).get("got"))
    return f'''<div class="toy single{' got' if got else ''}" data-code="{E(code)}" data-src="{E(t.get('source',''))}" data-name="{E(t.get('name',''))}">
  <div class="imgbox"><img loading="lazy" src="{E(img_of(t))}" alt="{E(t.get('name',''))}"></div>
  <div class="info">
    <h4>{E(t.get('name',''))}</h4>
    <p class="meta">{E(meta_line(t))}</p>
    <p class="code">code {E(code)}{avail_badge(t)}</p>
  </div>
  <button class="btn">{'★ 已点亮' if got else '☆ 点亮'}</button>
  <div class="stamp">{'已收集' if got else '未点亮'}</div>
</div>'''


# ---------- 系列卡（展开成单品槽位） ----------
def series_card(t):
    code = str(t["code"])
    slots = SLOTS.get(code) or []
    lineup = int(t.get("lineupCount") or 0)
    total = max(lineup, len(slots))
    got = sum(1 for s in slots if s.get("got"))
    chips = []
    for s in slots:
        nm = (s.get("name") or "").strip() or f"单品{s['slot']}"
        chips.append(
            f'<span class="chip{" got" if s.get("got") else ""}" data-slot="{s["slot"]}">'
            f'<i class="nm">{"★ " if s.get("got") else ""}{E(nm)}</i><b class="pen" title="给这款起名">✎</b></span>')
    chips.append('<span class="chip add" data-slot="add" title="添加一款（拿到的新款）">＋</span>')
    if total:
        head = f'一套 {total} 款 · 已收集 <b class="lu-got">{got}</b>/<span class="lu-total">{total}</span>'
    else:
        head = f'随机款 · 已记录 <b class="lu-got">{got}</b> 款（点 ＋ 添加拿到的款）'
    return f'''<div class="toy series{' got' if got else ''}" data-code="{E(code)}" data-src="{E(t.get('source',''))}" data-name="{E(t.get('name',''))}" data-lineup="{lineup}" data-got="{got}">
  <div class="imgbox"><img loading="lazy" src="{E(img_of(t))}" alt="{E(t.get('name',''))}"></div>
  <div class="info">
    <h4>{E(t.get('name',''))}</h4>
    <p class="meta">{E(meta_line(t))}</p>
    <p class="code">code {E(code)}{avail_badge(t)}</p>
  </div>
  <div class="lineup">
    <div class="lu-head">{head}</div>
    <div class="chips">{''.join(chips)}</div>
  </div>
</div>'''


def card(t):
    return series_card(t) if t.get("isSeries") else single_card(t)


def grid(items):
    return f'<div class="grid">{"".join(card(t) for t in items)}</div>' if items \
        else '<p class="desc">暂无数据</p>'


cur = [t for t in ALL if t["source"] == "current"]
his = [t for t in ALL if t["source"] == "history"]
mal = [t for t in ALL if t["source"] == "mall"]

# ---------- 收藏进度（单品级） ----------
def toy_total(t):
    if t.get("isSeries"):
        return max(int(t.get("lineupCount") or 0), len(SLOTS.get(str(t["code"])) or []))
    return 1


def toy_got(t):
    if t.get("isSeries"):
        return sum(1 for s in (SLOTS.get(str(t["code"])) or []) if s.get("got"))
    return 1 if SINGLE.get(str(t["code"]), {}).get("got") else 0


total = sum(toy_total(t) for t in ALL)
got = sum(toy_got(t) for t in ALL)

hot = None
if cur:
    hot = max(cur, key=lambda t: len(AVAIL_BY_TOY.get(str(t["code"]), {}).get("stores") or []))
hot_avail = AVAIL_BY_TOY.get(str(hot["code"]), {}) if hot else {}
hot_stores = hot_avail.get("stores") or []
hot_cities = sorted({s["city"] for s in hot_stores})

# ---------- 热门精选：热送卡 + 活动 + 周边推荐 ----------
if hot:
    hot_html = f'''<div class="hot">
  <img loading="lazy" src="{E(hot.get('image',''))}" alt="{E(hot.get('name',''))}">
  <div class="txt">
    <span class="ribbon">当前热送</span>
    <h3>{E(hot.get('name',''))}</h3>
    <p class="meta">{E(meta_line(hot))}</p>
    <p class="cov">实测覆盖：<b>{len(hot_stores)}</b> 家门店 · <b>{len(hot_cities)}</b> 座城市
      {'（' + E('、'.join(hot_cities)) + '）' if hot_cities else ''}</p>
    <div class="tagwrap">
      <span class="tag2">code {E(str(hot.get('code')))}</span>
      {'<span class="tag2">' + E(str(hot.get('round',''))) + '</span>' if hot.get('round') else ''}
      {'<span class="tag2">差价 ' + E(str(hot.get('diffPrice'))) + '</span>' if hot.get('diffPrice') else ''}
      {'<span class="tag2">一套 ' + E(str(hot.get('lineupCount') or 0)) + ' 款随机</span>' if hot.get('isSeries') else ''}
    </div>
    <p class="hint">数据源：<code>query-meal-detail</code> 的选配轮次 + <code>query-nearby-stores</code> 跨城门店校验</p>
  </div>
</div>'''
else:
    hot_html = '<p class="desc">当前门店未返回玩具选配项</p>'

events_html = "".join(
    f'''<div class="ev">{('<img loading="lazy" src="' + E(e["image"]) + '" alt="">') if e.get("image") else ''}
    <div><h4>{E(e["title"])}</h4><p>{E((e.get("desc") or "")[:170])}</p></div></div>'''
    for e in {(e["title"], e.get("desc", "")): e for e in toys_doc.get("events", [])}.values())

mall_html = grid(mal)

# ---------- 找玩具：门店清单 ----------
stores = avail_doc.get("stores") or []
open_stores = [s for s in stores if s.get("open")]
row_html = []
for s in sorted(stores, key=lambda x: (not x.get("open"), x.get("city", ""), x.get("storeName", ""))):
    names = "、".join(dict.fromkeys(t["name"] for t in s.get("toys") or [])) or "—"
    state = ('<span class="pill ok">营业中</span>' if s.get("open")
             else f'<span class="pill no">不可点餐</span>')
    row_html.append(f'''<tr data-city="{E(s.get('city',''))}" data-open="{'1' if s.get('open') else '0'}">
      <td>{E(s.get('storeName',''))}<br><span class="addr">{E(s.get('address') or '')}</span></td>
      <td>{E(s.get('city',''))}</td>
      <td class="c">{E(s.get('storeCode',''))}</td>
      <td>{names}</td>
      <td>{state}{('<br><span class="why">' + E(str(s.get('reason',''))) + '</span>') if s.get('reason') else ''}</td>
    </tr>''')

scan = {"at": avail_doc.get("scannedAt", ""), "cities": avail_doc.get("cityCount", 0),
        "stores": avail_doc.get("storeCount", 0), "open": avail_doc.get("openStoreCount", 0),
        "toys": avail_doc.get("toyCount", 0)}

HTML = f"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>开心乐园餐 · 玩具收藏与找玩具</title>
<style>
:root{{--bg:#fff9ec;--panel:#fff;--line:#ecdfc0;--text:#241a06;--muted:#8a7a55;--red:#DA291C;--yellow:#FFC72C;--gold:#e8b923}}
*{{box-sizing:border-box}}
body{{margin:0;background:var(--bg);color:var(--text);font:14px/1.6 "PingFang SC","Microsoft YaHei",sans-serif}}
.wrap{{max-width:1180px;margin:0 auto;padding:24px 20px 70px}}
header.top{{background:linear-gradient(120deg,#DA291C,#FFC72C 125%);color:#fff;border-radius:18px;padding:24px 26px 20px}}
header.top h1{{margin:0 0 6px;font-size:25px}}
header.top p{{margin:0;font-size:13.5px;opacity:.95}}
.bar{{margin-top:14px;background:rgba(255,255,255,.3);border-radius:999px;height:12px;overflow:hidden}}
.bar i{{display:block;height:100%;background:#fff;width:{(got/total*100 if total else 0):.1f}%;border-radius:999px}}
.pline{{margin-top:7px;font-size:13px;display:flex;justify-content:space-between;flex-wrap:wrap;gap:8px}}
nav.tabs{{display:flex;gap:8px;margin:18px 0 4px;flex-wrap:wrap}}
nav.tabs label{{border:1px solid var(--line);background:#fff;border-radius:999px;padding:8px 18px;font-size:13.5px;cursor:pointer;color:#6b5a33;user-select:none}}
nav.tabs label:hover{{border-color:var(--gold)}}
/* Tab 用 radio + :checked 实现，不依赖 JS：预览面板沙箱禁用 localStorage/JS 时也能切换 */
.tb{{position:absolute;left:-9999px;width:1px;height:1px;opacity:0}}
.page{{display:none}}
#t-hot:checked ~ #p-hot,#t-coll:checked ~ #p-coll,#t-find:checked ~ #p-find{{display:block}}
#t-hot:checked ~ nav.tabs label[for="t-hot"],
#t-coll:checked ~ nav.tabs label[for="t-coll"],
#t-find:checked ~ nav.tabs label[for="t-find"]{{background:var(--red);border-color:var(--red);color:#fff;font-weight:600}}
.hot{{background:var(--panel);border:2px solid var(--gold);border-radius:16px;padding:18px;display:flex;gap:18px;align-items:center;flex-wrap:wrap}}
.hot img{{width:200px;height:200px;object-fit:contain;background:#fff;border-radius:12px}}
.hot .txt{{flex:1;min-width:250px}}
.hot h3{{margin:2px 0 6px;font-size:20px}}
.hot .meta{{margin:0;font-size:12.5px;color:var(--muted)}}
.hot .cov{{margin:8px 0 6px;font-size:13px}}
.ribbon{{display:inline-block;background:var(--red);color:#fff;font-size:11.5px;border-radius:6px;padding:2px 9px}}
.hot .hint{{margin:8px 0 0;font-size:12.3px;color:#7d6a41}}
section{{margin:24px 0}}
h2{{font-size:18px;margin:0 0 10px;display:flex;align-items:center;gap:8px}}
h2::before{{content:"";width:4px;height:16px;background:var(--red);border-radius:2px}}
h2 .cnt{{background:#f2e6c4;color:var(--muted);border-radius:999px;font-size:12px;padding:1px 8px;font-weight:400}}
.desc{{font-size:12.5px;color:var(--muted);margin:0 0 10px}}
.grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(196px,1fr));gap:14px}}
.grp{{margin-top:18px}}
.grp h3{{font-size:15px;margin:0 0 10px;display:flex;align-items:center;gap:8px}}
.grp h3 .cnt{{background:#f2e6c4;color:var(--muted);border-radius:999px;font-size:11.5px;padding:1px 8px;font-weight:400}}
/* ---- 单品卡 ---- */
.toy{{background:var(--panel);border:1px solid var(--line);border-radius:14px;padding:12px;position:relative;display:flex;flex-direction:column;gap:8px;transition:.18s}}
.toy .imgbox{{background:#fff;border-radius:10px;height:150px;display:flex;align-items:center;justify-content:center;overflow:hidden}}
.toy img{{max-width:100%;max-height:100%;object-fit:contain;filter:grayscale(1) opacity(.5)}}
.toy.got{{border-color:var(--gold);box-shadow:0 3px 12px rgba(232,185,35,.3)}}
.toy.got img{{filter:none;opacity:1}}
.toy h4{{margin:0;font-size:14px}}
.toy .meta{{margin:0;font-size:11.5px;color:var(--muted)}}
.toy .code{{margin:0;font-size:11px;color:#b3a483}}
.badge{{margin-left:6px;font-size:10.5px;border-radius:5px;padding:1px 6px}}
.b-avail{{background:#e7f5ea;color:#2c7a45}}
.btn{{border:1px solid var(--line);background:#fff8e6;border-radius:8px;padding:6px;font-size:13px;cursor:pointer;color:#7a5c00}}
.toy.got .btn{{background:var(--gold);border-color:var(--gold);color:#3d2c00;font-weight:600}}
.stamp{{position:absolute;top:8px;right:8px;font-size:11px;background:#f1f2f4;color:#8a8a8a;border-radius:5px;padding:1px 7px}}
.toy.got .stamp{{background:var(--gold);color:#3d2c00}}
/* ---- 系列卡：单品槽位 ---- */
.toy.series{{grid-column:1/-1;flex-direction:row;flex-wrap:wrap;align-items:flex-start;gap:14px}}
.toy.series .imgbox{{width:150px;height:150px;flex:none}}
.toy.series .info{{flex:1;min-width:200px}}
.lineup{{flex:1 1 100%;border-top:1px dashed var(--line);padding-top:10px}}
.lu-head{{font-size:12.5px;color:#6b5a33;margin-bottom:8px}}
.lu-head b{{color:var(--red)}}
.chips{{display:flex;flex-wrap:wrap;gap:7px}}
.chip{{display:inline-flex;align-items:center;gap:4px;border:1px solid var(--line);background:#f6f2e6;color:#9a8a63;border-radius:999px;padding:4px 10px;font-size:12.3px;cursor:pointer;user-select:none;transition:.15s}}
.chip:hover{{border-color:var(--gold)}}
.chip.got{{background:var(--gold);border-color:var(--gold);color:#3d2c00;font-weight:600}}
.chip .pen{{font-style:normal;font-size:10.5px;opacity:.45;border-radius:4px;padding:0 2px}}
.chip .pen:hover{{opacity:1;background:rgba(0,0,0,.08)}}
.chip.add{{background:#fff;border-style:dashed;color:#b3a483;font-weight:700}}
.chip input{{border:1px solid var(--gold);border-radius:6px;padding:1px 6px;font-size:12.3px;width:96px;font-family:inherit}}
.filters{{display:flex;gap:8px;flex-wrap:wrap;margin:0 0 12px;align-items:center}}
.filters input,.filters select{{border:1px solid var(--line);border-radius:8px;padding:7px 10px;font-size:13px;background:#fff;color:var(--text)}}
.tagwrap{{display:flex;gap:6px;flex-wrap:wrap}}
.tag2{{display:inline-block;background:#fff3cf;color:#8a6100;border-radius:6px;padding:2px 9px;font-size:12px}}
.ev{{display:flex;gap:12px;background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:10px;margin-bottom:10px}}
.ev img{{width:110px;height:78px;object-fit:cover;border-radius:8px}}
.ev h4{{margin:0 0 4px;font-size:14px}}
.ev p{{margin:0;font-size:12.3px;color:var(--muted)}}
table{{width:100%;border-collapse:collapse;background:#fff;border:1px solid var(--line);border-radius:12px;overflow:hidden}}
th,td{{padding:9px 10px;font-size:12.6px;border-bottom:1px solid #f2e9d2;text-align:left;vertical-align:top}}
th{{background:#fff3cf;color:#7a5c00;font-weight:600}}
td.c{{color:#b3a483;font-size:11.5px}}
.addr{{color:var(--muted);font-size:11.5px}}
.pill{{display:inline-block;border-radius:6px;padding:1px 8px;font-size:11.5px}}
.pill.ok{{background:#e7f5ea;color:#2c7a45}} .pill.no{{background:#f4f4f5;color:#8a8a8a}}
.why{{color:#b3a483;font-size:11px}}
.tip{{background:#fff8e6;border:1px solid var(--line);border-radius:12px;padding:12px 14px;font-size:12.6px;color:#6b5a33;line-height:1.75}}
footer{{margin-top:28px;text-align:center;font-size:12.3px;color:var(--muted)}}
</style></head><body><div class="wrap">
<input type="radio" name="tab" id="t-hot" class="tb" checked>
<input type="radio" name="tab" id="t-coll" class="tb">
<input type="radio" name="tab" id="t-find" class="tb">
<header class="top">
  <h1>开心乐园餐 · 玩具收藏与找玩具</h1>
  <p>全部数据来自麦当劳 MCP Server 只读接口 · 玩具图片取自官方图床 · 每份乐园餐含随机玩具 1 个，按单品点亮</p>
  <div class="bar"><i></i></div>
  <div class="pline">
    <span>收藏进度 <b id="got">{got}</b> / {total}</span>
    <span>总库 {E(toys_doc.get('generatedAt',''))} · 门店扫描 {E(str(scan['at']))}</span>
  </div>
</header>

<nav class="tabs">
  <label for="t-hot">🔥 热门精选</label>
  <label for="t-coll">📖 电子收藏册</label>
  <label for="t-find">🔍 找玩具</label>
</nav>

<div class="page" id="p-hot">
  <section style="margin-top:0">
    <h2>当前热送<span class="cnt">1</span></h2>
    <p class="desc">全国统一配送的当期联名玩具，数据实时来自套餐选配轮次</p>
    {hot_html}
  </section>
  <section>
    <h2>相关活动<span class="cnt">{len(toys_doc.get('events', []))}</span></h2>
    {events_html or '<p class="desc">暂无活动</p>'}
  </section>
  <section>
    <h2>积分兑换周边<span class="cnt">{len(mal)}</span></h2>
    <p class="desc">来自 <code>mall-points-products</code>（catRuleIds=2&gt;8 玩具类目），点击卡片可整体点亮</p>
    {mall_html}
  </section>
</div>

<div class="page" id="p-coll">
  <section style="margin-top:0">
    <h2>收藏册<span class="cnt">{total}</span></h2>
    <p class="desc">每份开心乐园餐含<b>随机玩具 1 个</b>——系列卡按单品点亮：点芯片点亮/取消，点 <b>✎</b> 给这款起名，
      点 <b>＋</b> 添加拿到的新款。状态保存在本机 localStorage。</p>
    <div class="filters">
      <input id="q" placeholder="搜索玩具名称 / 单品名 / code" autocomplete="off">
      <select id="f">
        <option value="">全部分类</option>
        <option value="current">当前在售 {len(cur)}</option>
        <option value="history">历史款 {len(his)}</option>
        <option value="mall">积分兑换 {len(mal)}</option>
      </select>
      <select id="g">
        <option value="">全部状态</option>
        <option value="started">已有收集</option>
        <option value="todo">尚未开始</option>
        <option value="done">已收集齐</option>
      </select>
      <button class="btn" id="export">导出我的收藏</button>
    </div>
    <div class="grp" data-g="current">
      <h3>🔥 当前在送<span class="cnt">{len(cur)}</span></h3>
      {grid(cur)}
    </div>
    <div class="grp" data-g="history">
      <h3>🕓 历史款 · 我订单里拿到过的<span class="cnt">{len(his)}</span></h3>
      <p class="desc">来自 <code>order-list</code> 真实订单解析，标注下单日期；已下市的款式同样收录</p>
      {grid(his)}
    </div>
    <div class="grp" data-g="mall">
      <h3>🎁 积分兑换周边<span class="cnt">{len(mal)}</span></h3>
      <p class="desc">来自 <code>mall-points-products</code>，含往期限量兑换活动（卡片标注积分与时间）</p>
      {grid(mal)}
    </div>
  </section>
</div>

<div class="page" id="p-find">
  <section style="margin-top:0">
    <h2>找玩具 · 门店可得性<span class="cnt">{scan['stores']}</span></h2>
    <p class="desc">扫描时间 {E(str(scan['at']))} · 覆盖 {scan['cities']} 座城市 / {scan['stores']} 家门店，
      其中 <b>{scan['open']}</b> 家当时营业并可点餐，识别到 {scan['toys']} 款在送玩具。
      「不可点餐」多为门店打烊（返回 600057），白天重跑 <code>scan_toys.py</code> 可显著提高覆盖率。</p>
    <div class="filters">
      <input id="sq" placeholder="搜索门店 / 城市 / 玩具 / code" autocomplete="off">
      <select id="sc"><option value="">全部城市</option>
        {''.join('<option value="' + E(c) + '">' + E(c) + '</option>' for c in sorted({s.get('city','') for s in stores}))}
      </select>
      <label style="font-size:12.6px;color:#6b5a33"><input type="checkbox" id="so"> 只看营业中</label>
    </div>
    <table>
      <thead><tr><th>门店</th><th>城市</th><th>code</th><th>当前在送玩具</th><th>状态</th></tr></thead>
      <tbody id="sb">{''.join(row_html) or '<tr><td colspan="5">暂无扫描数据，先运行 scripts/scan_toys.py</td></tr>'}</tbody>
    </table>
  </section>
  <div class="tip">
    <b>刷新数据</b>：<br>
    <code>python scripts/scan_toys.py --per-city 8</code>　跨 6 城采样门店并写入 <code>data/availability.json</code><br>
    <code>python scripts/scan_toys.py --cities 深圳市,广州市 --per-city 12</code>　指定城市与门店密度<br>
    <code>python scripts/catalog.py</code>　重建玩具总库（当前款 / 历史订单 / 积分周边 / 活动）<br>
    <code>python scripts/collection.py collect 521991 --slot 3 --name "路飞"</code>　命令行点亮系列内第 3 款<br>
    <code>python scripts/collection.py add 7001 --name "抽到的某款"</code>　给随机玩具追加一款记录<br>
    门店检索注意：<code>query-nearby-stores</code> 的 <code>searchType=2</code> 必须 <b>city 与 keyword 同时传</b>，
    只传其一会报 <code>600058</code>。
  </div>
</div>

<footer>数据来源：麦当劳中国 MCP Server（mcp.mcd.cn）· 仅用于学习与技术验证，非麦当劳官方产品</footer>
</div>
<script>
/* 存储兜底：预览面板沙箱 iframe / 隐私模式下访问 localStorage 会抛 SecurityError，
   旧版脚本第一行就死掉 → Tab、点亮、筛选全部失效。这里统一 try/catch + 内存回退；
   Tab 切换本身已改为纯 CSS（radio + :checked），即使 JS 整体不可用也能切换页面。 */
var KEY='mcd_toy_collection_v1', mem={{}};
function loadState(){{
  try{{var raw=localStorage.getItem(KEY);return raw?JSON.parse(raw):{{}};}}catch(e){{return mem;}}
}}
function saveState(s){{
  mem=s;
  try{{localStorage.setItem(KEY,JSON.stringify(s));}}catch(e){{}}
}}
/* 初始状态来自服务端渲染的 data/collection.json（单品级），localStorage 优先 */
var INIT={INIT_JSON};
var got=loadState();
if(!got||!got.slots){{got=JSON.parse(JSON.stringify(INIT));}}
var root=document.body;
function slotsOf(c){{return (got.slots[String(c)]=got.slots[String(c)]||[]);}}
function lineupTotal(card){{
  var lu=parseInt(card.getAttribute('data-lineup')||'0',10)||0;
  return Math.max(lu,slotsOf(card.dataset.code).length);
}}
function paintSingle(el,on){{
  el.classList.toggle('got',on);
  var b=el.querySelector('.btn'); if(b) b.textContent=on?'★ 已点亮':'☆ 点亮';
  var st=el.querySelector('.stamp'); if(st) st.textContent=on?'已收集':'未点亮';
}}
/* 同一款玩具可能在多个分区出现（如积分周边同时出现在热门精选与收藏册），点亮时同步全部副本 */
function paintAll(c,on){{
  root.querySelectorAll('.toy[data-code="'+c+'"]').forEach(function(el){{paintSingle(el,on);}});
}}
function refreshCard(card){{
  var c=card.dataset.code, arr=slotsOf(c);
  var n=0; arr.forEach(function(s){{if(s.got)n++;}});
  var g=card.querySelector('.lu-got'); if(g) g.textContent=n;
  var t=card.querySelector('.lu-total'); if(t) t.textContent=lineupTotal(card);
  card.classList.toggle('got',n>0);
  card.setAttribute('data-got',n);
}}
function countGot(){{
  var n=0;
  root.querySelectorAll('.toy.series').forEach(function(card){{
    slotsOf(card.dataset.code).forEach(function(s){{if(s.got)n++;}});
  }});
  root.querySelectorAll('.toy.single').forEach(function(card){{
    if(got.single&&got.single[card.dataset.code]&&got.single[card.dataset.code].got)n++;
  }});
  return n;
}}
function countTotal(){{
  var n=0;
  root.querySelectorAll('.toy.series').forEach(function(card){{n+=lineupTotal(card);}});
  n+=root.querySelectorAll('.toy.single').length;
  return n;
}}
function syncCount(){{
  var cnt=document.getElementById('got'); if(cnt) cnt.textContent=String(countGot())+'/'+String(countTotal());
}}
function refreshAll(){{
  root.querySelectorAll('.toy.series').forEach(refreshCard);
  Object.keys(got.single||{{}}).forEach(function(c){{
    if(got.single[c].got) paintAll(c,true);
  }});
  syncCount();
}}
/* ---- 点击：单品芯片 / 起名 / 添加 / 单品整体点亮 ---- */
root.addEventListener('click',function(ev){{
  var t=ev.target;
  if(!(t instanceof Element)) return;
  var pen=t.closest('.chip .pen');
  if(pen){{ startRename(pen.parentNode); return; }}
  var add=t.closest('.chip.add');
  if(add){{ addSlot(add.closest('.toy')); return; }}
  var chip=t.closest('.chip');
  if(chip&&chip.closest('.toy.series')){{
    var card=chip.closest('.toy'), c=card.dataset.code, slot=parseInt(chip.dataset.slot,10);
    var arr=slotsOf(c), s=null;
    for(var i=0;i<arr.length;i++) if(arr[i].slot===slot) s=arr[i];
    if(!s){{s={{slot:slot,name:'',got:false,at:'',store:''}};arr.push(s);}}
    s.got=!s.got;
    if(s.got) s.at=new Date().toISOString().slice(0,10); else s.at='';
    paintChip(chip,s);
    refreshCard(card);
    saveState(got); syncCount(); applyFilter();
    return;
  }}
  var b=t.closest('.toy.single .btn');
  if(b){{
    var el=b.closest('.toy'), code=el.dataset.code;
    var on=!(got.single&&got.single[code]&&got.single[code].got);
    got.single=got.single||{{}};
    if(on) got.single[code]={{got:true,at:new Date().toISOString().slice(0,10),store:''}};
    else delete got.single[code];
    paintAll(code,on);
    saveState(got); syncCount(); applyFilter();
  }}
}});
function paintChip(chip,s){{
  chip.classList.toggle('got',!!s.got);
  var nm=(s.name||'').trim()||('单品'+s.slot);
  chip.querySelector('.nm').textContent=(s.got?'★ ':'')+nm;
}}
/* ---- 起名（行内编辑） ---- */
function startRename(chip){{
  if(chip.querySelector('input')) return;
  var s=null,arr=slotsOf(chip.closest('.toy').dataset.code),slot=parseInt(chip.dataset.slot,10);
  for(var i=0;i<arr.length;i++) if(arr[i].slot===slot) s=arr[i];
  var old=s&&s.name?s.name:'';
  var nm=chip.querySelector('.nm');
  var inp=document.createElement('input');
  inp.value=old; inp.placeholder='这款叫什么？';
  var closed=false;
  /* 提交不依赖 blur：Enter 直接落库，避免 input 未获焦时 blur 不触发导致改名丢失 */
  function commit(){{
    if(closed) return; closed=true;
    var v=inp.value.trim();
    if(s){{ s.name=v; }}
    else if(v){{ s={{slot:slot,name:v,got:chip.classList.contains('got'),at:'',store:''}}; arr.push(s); }}
    inp.remove(); nm.style.display='';
    paintChip(chip,{{slot:slot,name:(s&&s.name)||'',got:chip.classList.contains('got')}});
    saveState(got);
  }}
  nm.style.display='none';
  chip.appendChild(inp);
  try{{inp.focus(); inp.select();}}catch(e){{}}
  inp.addEventListener('blur',commit);
  inp.addEventListener('keydown',function(e){{
    if(e.key==='Enter'){{e.preventDefault(); commit();}}
    else if(e.key==='Escape'){{inp.value=old; commit();}}
  }});
  inp.addEventListener('click',function(e){{e.stopPropagation();}});
}}
/* ---- 追加一款（随机玩具 / 超出预置款数） ---- */
function addSlot(card){{
  if(!card) return;
  var c=card.dataset.code, arr=slotsOf(c);
  var s={{slot:arr.length+1,name:'',got:false,at:'',store:''}};
  arr.push(s);
  var chip=document.createElement('span');
  chip.className='chip'; chip.dataset.slot=String(s.slot);
  chip.innerHTML='<i class="nm">'+s.slot+'</i><b class="pen" title="给这款起名">✎</b>';
  card.querySelector('.chips').insertBefore(chip,card.querySelector('.chip.add'));
  refreshCard(card); saveState(got); syncCount();
  startRename(chip);
}}
/* ---- 筛选 ---- */
var q=document.getElementById('q'),f=document.getElementById('f'),g=document.getElementById('g');
function cardState(card){{
  if(card.classList.contains('series')){{
    var n=parseInt(card.getAttribute('data-got')||'0',10);
    var t=lineupTotal(card);
    return n===0?'todo':(n>=t?'done':'started');
  }}
  return card.classList.contains('got')?'done':'todo';
}}
function applyFilter(){{
  var kw=(q.value||'').trim().toLowerCase();
  root.querySelectorAll('.toy').forEach(function(el){{
    var text=(el.dataset.name+' '+el.dataset.code+' '+el.textContent).toLowerCase();
    var okKw=!kw||text.indexOf(kw)>=0;
    var okF=!f.value||el.dataset.src===f.value;
    var st=cardState(el);
    var okG=!g.value||(g.value==='started'?st!=='todo':(g.value==='todo'?st==='todo':st==='done'));
    el.style.display=(okKw&&okF&&okG)?'':'none';
  }});
  root.querySelectorAll('.grp').forEach(function(grp){{
    var any=false;
    grp.querySelectorAll('.toy').forEach(function(el){{ if(el.style.display!=='none') any=true; }});
    grp.style.display=any?'':'none';
  }});
}}
[q,f,g].forEach(function(x){{x.addEventListener('input',applyFilter);}});
document.getElementById('export').addEventListener('click',function(){{
  var rows=[['kind','code','name','slot','name_of_toy','at']];
  root.querySelectorAll('.toy.series').forEach(function(card){{
    slotsOf(card.dataset.code).forEach(function(s){{
      rows.push(['series',card.dataset.code,card.dataset.name,s.slot,(s.name||'').replace(/,/g,'，'),s.at||'']);
    }});
  }});
  root.querySelectorAll('.toy.single').forEach(function(card){{
    var on=got.single&&got.single[card.dataset.code]&&got.single[card.dataset.code].got;
    rows.push(['single',card.dataset.code,card.dataset.name,'','',on?(got.single[card.dataset.code].at||''):'']);
  }});
  var csv=rows.map(function(r){{return r.join(',');}}).join('\\n');
  var blob=new Blob([csv],{{type:'text/csv'}});
  var a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download='my_toys.csv';a.click();
}});
/* ---- 门店筛选 ---- */
var sq=document.getElementById('sq'),sc=document.getElementById('sc'),so=document.getElementById('so');
function filterStores(){{
  var kw=(sq.value||'').trim().toLowerCase();
  document.querySelectorAll('#sb tr').forEach(function(tr){{
    var okCity=!sc.value||tr.dataset.city===sc.value;
    var okOpen=!so.checked||tr.dataset.open==='1';
    var okKw=!kw||tr.textContent.toLowerCase().indexOf(kw)>=0;
    tr.style.display=(okCity&&okOpen&&okKw)?'':'none';
  }});
}}
if(sq)[sq,sc,so].forEach(function(x){{x.addEventListener('input',filterStores);}});
refreshAll();
</script>
</body></html>"""

WEB.mkdir(parents=True, exist_ok=True)
out = WEB / "index.html"
out.write_text(HTML, encoding="utf-8")
print("written", out, len(HTML), "bytes | toys", len(ALL), "| slots", got, "/", total, "| stores", len(stores))
