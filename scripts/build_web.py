# -*- coding: utf-8 -*-
"""生成单文件玩具站 web/index.html（热门精选 / 电子收藏册 / 找玩具）。

数据来源：data/toys.json（总库）+ data/availability.json（跨城门店可得性）
两张表都由 scripts/*.py 通过麦当劳 MCP Server 只读接口拉取，不写死任何业务数据。
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
    if (DATA / "collection.json").exists() else {"collected": {}}

ALL = toys_doc.get("toys", [])
# 门店可用性按玩具 code 汇总，供前端展示"哪些店有"（键统一转 str，防类型漂移）
AVAIL_BY_TOY = {str(t["code"]): t for t in avail_doc.get("toys", [])}


def meta_line(t):
    bits = []
    for key, suffix in (("status", ""), ("round", ""), ("point", " 积分"),
                        ("storeName", ""), ("series", "")):
        v = t.get(key)
        if v:
            bits.append(f"{v}{suffix}")
    if str(t.get("diffPrice") or "").strip() not in ("", "+ ¥0", "+¥0", "0", "None"):
        bits.append(f"差价 {t['diffPrice']}")
    if t.get("price") and str(t["price"]) not in ("0", ""):
        bits.append(f"¥{t['price']}")
    return " · ".join(bits)


def card(t):
    code = str(t["code"])
    got = code in coll_doc["collected"]
    info = coll_doc["collected"].get(code, {})
    img = t.get("image") or ""
    avail = AVAIL_BY_TOY.get(code, {})
    n_store = len(avail.get("stores") or [])
    badge = f'<span class="badge b-avail">{n_store} 家门店在送</span>' if n_store else ""
    return f'''<div class="toy{' got' if got else ''}" data-code="{E(code)}" data-src="{E(t.get('source',''))}" data-name="{E(t.get('name',''))}">
  <div class="imgbox"><img loading="lazy" src="{E(img)}" alt="{E(t.get('name',''))}"></div>
  <div class="info">
    <h4>{E(t.get('name',''))}</h4>
    <p class="meta">{E(meta_line(t))}</p>
    <p class="code">code {E(code)}{badge}</p>
  </div>
  <button class="btn">{'★ 已点亮' if got else '☆ 点亮'}</button>
  <div class="stamp">{'已收集' if got else '未点亮'}</div>
  {('<div class="at">'+E(str(info.get("at","")))+'</div>') if got and info.get("at") else ''}
</div>'''


def grid(items):
    return f'<div class="grid">{"".join(card(t) for t in items)}</div>' if items \
        else '<p class="desc">暂无数据</p>'


cur = [t for t in ALL if t["source"] == "current"]
his = [t for t in ALL if t["source"] == "history"]
mal = [t for t in ALL if t["source"] == "mall"]

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

total = len(ALL)
got = len(coll_doc["collected"])

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
nav.tabs button{{border:1px solid var(--line);background:#fff;border-radius:999px;padding:8px 18px;font-size:13.5px;cursor:pointer;color:#6b5a33}}
nav.tabs button.on{{background:var(--red);border-color:var(--red);color:#fff;font-weight:600}}
.page{{display:none}} .page.on{{display:block}}
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
.at{{font-size:11px;color:var(--muted);text-align:right}}
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
<header class="top">
  <h1>开心乐园餐 · 玩具收藏与找玩具</h1>
  <p>全部数据来自麦当劳 MCP Server 只读接口 · 玩具图片取自官方图床</p>
  <div class="bar"><i></i></div>
  <div class="pline">
    <span>收藏进度 <b id="got">{got}</b> / {total}</span>
    <span>总库 {E(toys_doc.get('generatedAt',''))} · 门店扫描 {E(str(scan['at']))}</span>
  </div>
</header>

<nav class="tabs">
  <button class="on" data-p="p-hot">🔥 热门精选</button>
  <button data-p="p-coll">📖 电子收藏册</button>
  <button data-p="p-find">🔍 找玩具</button>
</nav>

<div class="page on" id="p-hot">
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
    <p class="desc">来自 <code>mall-points-products</code>（catRuleIds=2&gt;8 玩具类目）</p>
    {mall_html}
  </section>
</div>

<div class="page" id="p-coll">
  <section style="margin-top:0">
    <h2>收藏册<span class="cnt">{total}</span></h2>
    <p class="desc">买到对应玩具就点亮它，状态保存在本机 localStorage；输入关键词可筛选</p>
    <div class="filters">
      <input id="q" placeholder="搜索玩具名称 / code" autocomplete="off">
      <select id="f">
        <option value="">全部分类</option>
        <option value="current">当前在售 {len(cur)}</option>
        <option value="history">历史款 {len(his)}</option>
        <option value="mall">积分兑换 {len(mal)}</option>
      </select>
      <select id="g">
        <option value="">全部状态</option>
        <option value="got">已点亮</option>
        <option value="todo">未点亮</option>
      </select>
      <button class="btn" id="export">导出我的收藏</button>
    </div>
    {grid(ALL)}
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
    <code>python scripts/collection.py collect 521991 --store 1420544</code>　命令行点亮玩具（写回 <code>data/collection.json</code>）<br>
    门店检索注意：<code>query-nearby-stores</code> 的 <code>searchType=2</code> 必须 <b>city 与 keyword 同时传</b>，
    只传其一会报 <code>600058</code>。
  </div>
</div>

<footer>数据来源：麦当劳中国 MCP Server（mcp.mcd.cn）· 仅用于学习与技术验证，非麦当劳官方产品</footer>
</div>
<script>
const KEY='mcd_toy_collection_v1';
let got=JSON.parse(localStorage.getItem(KEY)||'{{}}');
const root=document.body;
root.querySelectorAll('.toy').forEach(el=>{{
  const c=el.dataset.code;
  if(got[c]) {{
    el.classList.add('got');
    el.querySelector('.btn').textContent='★ 已点亮';
    el.querySelector('.stamp').textContent='已收集';
  }}
}});
root.addEventListener('click',ev=>{{
  const b=ev.target.closest('.toy .btn'); if(!b) return;
  const el=b.closest('.toy'), c=el.dataset.code;
  if(got[c]){{delete got[c];el.classList.remove('got');b.textContent='☆ 点亮';el.querySelector('.stamp').textContent='未点亮';}}
  else{{got[c]={{at:new Date().toISOString().slice(0,10)}};el.classList.add('got');b.textContent='★ 已点亮';el.querySelector('.stamp').textContent='已收集';}}
  localStorage.setItem(KEY,JSON.stringify(got));
  document.getElementById('got').textContent=Object.keys(got).length;
  applyFilter();
}});
document.querySelectorAll('nav.tabs button').forEach(b=>b.addEventListener('click',()=>{{
  document.querySelectorAll('nav.tabs button').forEach(x=>x.classList.remove('on'));
  document.querySelectorAll('.page').forEach(x=>x.classList.remove('on'));
  b.classList.add('on'); document.getElementById(b.dataset.p).classList.add('on');
}}));
const q=document.getElementById('q'),f=document.getElementById('f'),g=document.getElementById('g');
function applyFilter(){{
  const kw=(q.value||'').trim().toLowerCase();
  root.querySelectorAll('.toy').forEach(el=>{{
    const okKw=!kw||(el.dataset.name+' '+el.dataset.code).toLowerCase().includes(kw);
    const okF=!f.value||el.dataset.src===f.value;
    const okG=!g.value||(g.value==='got'?!!got[el.dataset.code]:!got[el.dataset.code]);
    el.style.display=(okKw&&okF&&okG)?'':'none';
  }});
}}
[q,f,g].forEach(x=>x.addEventListener('input',applyFilter));
document.getElementById('export').addEventListener('click',()=>{{
  const rows=Object.keys(got).map(c=>{{
    const el=root.querySelector('.toy[data-code="'+c+'"]');
    return c+','+(el?el.dataset.name:'')+','+got[c].at;
  }});
  const blob=new Blob([['code','name','at'].join(',')].concat(rows).join('\\n'),{{type:'text/csv'}});
  const a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download='my_toys.csv';a.click();
}});
const sq=document.getElementById('sq'),sc=document.getElementById('sc'),so=document.getElementById('so');
function filterStores(){{
  const kw=(sq.value||'').trim().toLowerCase();
  document.querySelectorAll('#sb tr').forEach(tr=>{{
    const okCity=!sc.value||tr.dataset.city===sc.value;
    const okOpen=!so.checked||tr.dataset.open==='1';
    const okKw=!kw||tr.textContent.toLowerCase().includes(kw);
    tr.style.display=(okCity&&okOpen&&okKw)?'':'none';
  }});
}}
if(sq)[sq,sc,so].forEach(x=>x.addEventListener('input',filterStores));
</script>
</body></html>"""

WEB.mkdir(parents=True, exist_ok=True)
out = WEB / "index.html"
out.write_text(HTML, encoding="utf-8")
print("written", out, len(HTML), "bytes | toys", total, "| stores", len(stores))
