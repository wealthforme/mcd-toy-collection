# -*- coding: utf-8 -*-
"""收藏册命令行：单品级点亮 / 取消 / 改名 / 查看进度。

开心乐园餐的赠品是「一整套系列里的随机一个」，因此点亮单位是**系列内的单品**，
不是整个系列。例：海绵宝宝×航海王系列一套 10 款，买到哪款就点亮哪一款。

  python collection.py list                                  总览（系列进度 + 单品明细）
  python collection.py collect 521991 --slot 3 --name "路飞"  点亮系列内第 3 款
  python collection.py uncollect 521991 --slot 3             取消点亮
  python collection.py add 7001 --name "抽到的某款"           追加一个单品槽（随机玩具/多于预置款）
  python collection.py rename 521991 --slot 3 --name "新名"   给单品起名
  python collection.py collect 17643                          点亮非系列单品（积分周边）
  python collection.py stats                                 查看进度
  python collection.py sync                                  重新扫描并合并新玩具

数据文件 data/collection.json（version 2）：
  slots:  { 系列code: [ {slot, name, got, at, store}, ... ] }   系列内单品，按 slot 序号
  single: { 单品code: {got, at, store} }                        非系列单品（积分周边等）一键点亮
"""
import argparse, json, pathlib, sys, time

ROOT = pathlib.Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
TOYS = DATA / "toys.json"
COLL = DATA / "collection.json"


def load_json(p, default):
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            return default
    return default


def save(p, obj):
    DATA.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, ensure_ascii=False, indent=1), encoding="utf-8")


def migrate(coll):
    """v1 {collected:{code:{...}}} -> v2 单品模型：旧记录落为该系列第 1 款已点亮。"""
    if coll.get("version") == 2:
        coll.setdefault("slots", {})
        coll.setdefault("single", {})
        return coll
    slots, single = {}, {}
    for code, info in (coll.get("collected") or {}).items():
        if not isinstance(info, dict):
            info = {}
        slots[str(code)] = [{"slot": 1, "name": info.get("note", ""), "got": True,
                             "at": info.get("at", ""), "store": info.get("store", "")}]
    return {"version": 2, "slots": slots, "single": single}


def seed_lineup(coll, toys):
    """按官方系列图点数（toys.json 的 lineupCount）把系列槽位补齐，未命名。"""
    changed = False
    for t in toys.get("toys", []):
        if not t.get("isSeries"):
            continue
        arr = coll["slots"].setdefault(str(t["code"]), [])
        while len(arr) < int(t.get("lineupCount") or 0):
            arr.append({"slot": len(arr) + 1, "name": "", "got": False, "at": "", "store": ""})
            changed = True
    return changed


def slots_of(coll, code):
    return coll["slots"].setdefault(str(code), [])


def ensure_slot(coll, code, slot):
    """保证第 slot 个槽位存在（用户可 add 超出预置数量）。"""
    arr = slots_of(coll, code)
    while len(arr) < slot:
        arr.append({"slot": len(arr) + 1, "name": "", "got": False, "at": "", "store": ""})
    return arr[slot - 1]


def progress(coll, code, lineup_count):
    """返回 (已点亮数, 总款数)。总款数取 max(预置 lineupCount, 实际槽位数)。"""
    arr = coll["slots"].get(str(code)) or []
    total = max(int(lineup_count or 0), len(arr))
    got = sum(1 for s in arr if s.get("got"))
    return got, total


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["list", "collect", "uncollect", "add", "rename", "stats", "sync"])
    ap.add_argument("code", nargs="?")
    ap.add_argument("--slot", type=int, default=1, help="系列内第几款（从 1 开始）")
    ap.add_argument("--name", default="", help="单品名")
    ap.add_argument("--store", default="")
    ap.add_argument("--note", default="")
    args = ap.parse_args()

    toys = load_json(TOYS, {"toys": []})
    coll = migrate(load_json(COLL, {}))
    idx = {str(t["code"]): t for t in toys.get("toys", [])}
    if seed_lineup(coll, toys):
        save(COLL, coll)  # 补齐官方单品数的空槽位

    if args.cmd == "sync":
        sys.path.insert(0, str(pathlib.Path(__file__).parent))
        from catalog import main as build
        build()
        print("收藏册数据已更新")
        return

    if args.cmd == "list":
        for t in toys.get("toys", []):
            code = str(t["code"])
            if t.get("isSeries"):
                got, total = progress(coll, code, t.get("lineupCount"))
                mark = "★" if got else "☆"
                print(f"{mark} [{code}] {t['name']:<26} {got}/{total} 款")
                for s in coll["slots"].get(code, []):
                    nm = s.get("name") or f"单品{s['slot']}"
                    print(f"    {'★' if s.get('got') else '☆'} {s['slot']:>2}. {nm}"
                          + (f"  ({s['at'][:10]})" if s.get("got") and s.get("at") else ""))
            else:
                info = coll["single"].get(code, {})
                print(f"{'★' if info.get('got') else '☆'} [{code}] {t['name']:<26} {t.get('status','')}")
        return

    if args.cmd == "stats":
        g = t_ = 0
        lines = []
        for src, label in [("current", "当前在送"), ("history", "历史款"), ("mall", "积分兑换")]:
            sg = st = 0
            for t in [x for x in toys.get("toys", []) if x["source"] == src]:
                code = str(t["code"])
                if t.get("isSeries"):
                    a, b = progress(coll, code, t.get("lineupCount"))
                    sg += a
                    st += b
                else:
                    st += 1
                    sg += 1 if coll["single"].get(code, {}).get("got") else 0
            g += sg
            t_ += st
            lines.append(f"  {label}: {sg}/{st}")
        print(f"收藏进度：{g}/{t_}  ({(g / t_ * 100 if t_ else 0):.0f}%)")
        print("\n".join(lines))
        return

    if not args.code:
        print("需要提供玩具 code")
        return
    if args.code not in idx:
        print(f"未知玩具 code: {args.code}（可先运行 scripts/catalog.py 重建总库）")
        return
    toy = idx[args.code]
    code = str(args.code)

    if not toy.get("isSeries"):
        # 非系列单品：整体点亮/取消
        if args.cmd == "collect":
            coll["single"][code] = {"got": True, "at": time.strftime("%Y-%m-%d %H:%M:%S"),
                                    "store": args.store or toy.get("storeName", "")}
            save(COLL, coll)
            print(f"已点亮：{toy['name']}")
        elif args.cmd == "uncollect":
            coll["single"].pop(code, None)
            save(COLL, coll)
            print(f"已取消点亮：{toy['name']}")
        else:
            print("该玩具不是系列款，无需指定 --slot；直接 collect/uncollect 即可")
        return

    if args.cmd == "add":
        arr = slots_of(coll, code)
        arr.append({"slot": len(arr) + 1, "name": args.name, "got": False,
                    "at": "", "store": ""})
        save(COLL, coll)
        print(f"已为「{toy['name']}」新增第 {len(arr)} 款槽位"
              + (f"：{args.name}" if args.name else "（未命名，可用 rename 起名）"))
        return

    if args.cmd == "rename":
        s = ensure_slot(coll, code, args.slot)
        if not args.name:
            print("rename 需要 --name")
            return
        s["name"] = args.name
        save(COLL, coll)
        print(f"已命名：{toy['name']} 第 {args.slot} 款 -> {args.name}")
        return

    if args.slot < 1:
        print("--slot 必须 >= 1")
        return
    s = ensure_slot(coll, code, args.slot)
    if args.name and not s.get("name"):
        s["name"] = args.name

    if args.cmd == "collect":
        s["got"] = True
        s["at"] = time.strftime("%Y-%m-%d %H:%M:%S")
        s["store"] = args.store or toy.get("storeName", "")
        if args.note:
            s["note"] = args.note
        save(COLL, coll)
        got, total = progress(coll, code, toy.get("lineupCount"))
        print(f"已点亮：{toy['name']} 第 {args.slot} 款"
              + (f"（{s['name']}）" if s.get("name") else "")
              + f"  进度 {got}/{total}")
    else:
        s["got"] = False
        s["at"] = ""
        save(COLL, coll)
        got, total = progress(coll, code, toy.get("lineupCount"))
        print(f"已取消点亮：{toy['name']} 第 {args.slot} 款  进度 {got}/{total}")


if __name__ == "__main__":
    main()
