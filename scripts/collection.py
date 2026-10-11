# -*- coding: utf-8 -*-
"""收藏册命令行：点亮 / 取消 / 查看进度。

  python collection.py list                 列出全部玩具与点亮状态
  python collection.py collect 521991       点亮（可加 --store "门店名" --note "备注"）
  python collection.py uncollect 521991     取消点亮
  python collection.py stats                查看进度
  python collection.py sync                 重新扫描并合并新玩具到收藏册
"""
import argparse, json, pathlib, sys, time

ROOT = pathlib.Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
TOYS = DATA / "toys.json"
COLL = DATA / "collection.json"


def load_json(p, default):
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8"))
    return default


def save(p, obj):
    DATA.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, ensure_ascii=False, indent=1), encoding="utf-8")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["list", "collect", "uncollect", "stats", "sync"])
    ap.add_argument("code", nargs="?")
    ap.add_argument("--store", default="")
    ap.add_argument("--note", default="")
    args = ap.parse_args()

    toys = load_json(TOYS, {"toys": []})
    coll = load_json(COLL, {"collected": {}})
    idx = {str(t["code"]): t for t in toys.get("toys", [])}

    if args.cmd == "list":
        for t in toys.get("toys", []):
            got = "★" if str(t["code"]) in coll["collected"] else "☆"
            print(f"{got} [{t['code']}] {t['name']:<28} {t.get('status','')}")
        print(f"\n进度 {len(coll['collected'])}/{len(toys.get('toys', []))}")
        return

    if args.cmd == "stats":
        total = len(toys.get("toys", []))
        got = len(coll["collected"])
        print(f"收藏进度：{got}/{total}  ({(got/total*100 if total else 0):.0f}%)")
        for src, label in [("current", "当前在售"), ("history", "历史款"), ("mall", "积分兑换")]:
            sub = [t for t in toys.get("toys", []) if t["source"] == src]
            hit = [t for t in sub if str(t["code"]) in coll["collected"]]
            print(f"  {label}: {len(hit)}/{len(sub)}")
        return

    if args.cmd == "sync":
        sys.path.insert(0, str(pathlib.Path(__file__).parent))
        from catalog import main as build
        build()
        print("收藏册数据已更新")
        return

    if not args.code:
        print("需要提供玩具 code")
        return
    if args.code not in idx:
        print(f"未知玩具 code: {args.code}（可先运行 scripts/catalog.py 重建总库）")
        return

    if args.cmd == "collect":
        coll["collected"][args.code] = {
            "at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "store": args.store or idx[args.code].get("storeName", ""),
            "note": args.note,
        }
        save(COLL, coll)
        print(f"已点亮：{idx[args.code]['name']}")
    else:
        coll["collected"].pop(args.code, None)
        save(COLL, coll)
        print(f"已取消点亮：{idx[args.code]['name']}")
    print(f"进度 {len(coll['collected'])}/{len(idx)}")


if __name__ == "__main__":
    main()
