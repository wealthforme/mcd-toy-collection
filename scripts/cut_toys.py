# -*- coding: utf-8 -*-
"""把官方系列整图切割成单品图（每个槽位一张透明 PNG）。

系列整图（MS_<code>_600.png）是 N 个单品的拼版图：透明背景 + 底部一行红字
「含随机玩具1个」。切割策略：
  1. 按 alpha 投影出行带（两行玩具）/ 列带（每行的单品）；
  2. 521325 第一行前两个单品相连，用人工分割点 x=217 切开（已用像素剖面验证）；
  3. 每个单元格带 padding 裁剪后再做紧致 trim，输出 RGBA PNG。

产出：
  web/assets/toys/<code>_<slot>.png   单品图（slot 从 1 开始，行优先）
  data/slot_images.json               code -> [{slot,name,img}] 供 build_web 使用
"""
import json
import pathlib

import numpy as np
from PIL import Image

ROOT = pathlib.Path(__file__).resolve().parent.parent
SRC = ROOT / "web" / "assets" / "series-src"
OUT = ROOT / "web" / "assets" / "toys"
OUT.mkdir(parents=True, exist_ok=True)

# 每个系列图的行带（由 alpha 行投影实测得到，已排除底部红字带 y518-550）
ROW_BANDS = {
    "521991": [(92, 264), (307, 475)],
    "521417": [(41, 237), (253, 488)],
    "521325": [(25, 238), (259, 492)],
}
# 521325 第一行「小丸子」与「相框」两个单品相连，列投影合并成一段 (12,418)，
# 像素剖面显示 x=214..218 仅剩细条连接 → 人工分割点 217
MANUAL_SPLIT = {"521325": {0: [217]}}  # 行索引 -> 该行内的人工分割 x 列表

# 单品默认名。521991 为海绵宝宝×航海王联名（中国区 10 款，与官方系列图逐一比对：
# 1 海绵宝宝草帽、2 珊迪松鼠、3 派大星、4 痞老板持 10t 锤、5 绿皮大胡子海盗=飞行荷兰人、
# 6 小蜗、7 章鱼哥黑西装金发、8 蟹老板、9 珍珍鲸鱼、10 史密提骷髅爆炸头）；
# 521417 / 521325 按可见造型描述命名。用户均可在页面 ✎ 改名。
DEFAULT_NAMES = {
    "521991": {
        1: "海绵宝宝×路飞", 2: "珊迪×奈美", 3: "派大星×索隆", 4: "痞老板×乌索普",
        5: "飞行荷兰人×黑胡子", 6: "小蜗×乔巴", 7: "章鱼哥×山治", 8: "蟹老板×甚平",
        9: "珍珍×罗宾", 10: "史密提×布鲁克",
    },
    "521417": {
        1: "小马宝莉·蓝", 2: "小马宝莉·粉", 3: "小马宝莉·紫",
        4: "变形金刚·大黄蜂", 5: "变形金刚·擎天柱", 6: "变形金刚·威震天",
    },
    "521325": {
        1: "小丸子抱雪球", 2: "小丸子相框", 3: "雪人储钱罐",
        4: "小丸子台历", 5: "雪橇", 6: "小丸子铅笔",
    },
}

PAD = 6          # 单元格外扩
TRIM_PAD = 2     # trim 后再留的边
ALPHA_MIN = 8    # 视为内容的最低 alpha


def col_bands(alpha, y0, y1):
    """在行带内按列投影切出单品列带。"""
    sub = alpha[y0:y1 + 1, :]
    col = (sub > ALPHA_MIN).sum(axis=0)
    bands, in_b = [], False
    for x in range(alpha.shape[1]):
        if col[x] > 2 and not in_b:
            s, in_b = x, True
        elif col[x] <= 2 and in_b:
            bands.append((s, x - 1))
            in_b = False
    if in_b:
        bands.append((s, alpha.shape[1] - 1))
    return bands


def tight_bbox(im):
    a = np.array(im)[:, :, 3]
    ys, xs = np.where(a > ALPHA_MIN)
    if len(xs) == 0:
        return None
    return xs.min(), ys.min(), xs.max(), ys.max()


def cut_series(code):
    src = SRC / f"MS_{code}_600.png"
    if not src.exists():
        print(f"!! 缺少源图 {src}")
        return []
    im = Image.open(src).convert("RGBA")
    alpha = np.array(im)[:, :, 3]
    W = alpha.shape[1]
    slots = []
    slot = 1
    for ri, (y0, y1) in enumerate(ROW_BANDS[code]):
        bands = col_bands(alpha, y0, y1)
        # 应用人工分割（把过宽的列带按分割点切开）
        if ri in MANUAL_SPLIT.get(code, {}):
            splits = MANUAL_SPLIT[code][ri]
            expanded = []
            for (a0, a1) in bands:
                if a1 - a0 > 250 and splits:  # 只处理合并的宽带
                    pts = [a0] + [p for p in splits if a0 < p < a1] + [a1]
                    expanded += [(pts[i], pts[i + 1]) for i in range(len(pts) - 1)]
                else:
                    expanded.append((a0, a1))
            bands = expanded
        for (x0, x1) in bands:
            cx0 = max(0, x0 - PAD)
            cy0 = max(0, y0 - PAD)
            cx1 = min(W, x1 + PAD + 1)
            cy1 = min(alpha.shape[0], y1 + PAD + 1)
            cell = im.crop((cx0, cy0, cx1, cy1))
            bb = tight_bbox(cell)
            if bb is None:
                continue
            bx0, by0, bx1, by1 = bb
            cell = cell.crop((max(0, bx0 - TRIM_PAD), max(0, by0 - TRIM_PAD),
                              min(cell.width, bx1 + TRIM_PAD + 1),
                              min(cell.height, by1 + TRIM_PAD + 1)))
            name = DEFAULT_NAMES.get(code, {}).get(slot, f"单品{slot}")
            fn = f"{code}_{slot}.png"
            cell.save(OUT / fn, optimize=True)
            slots.append({"slot": slot, "name": name, "img": f"assets/toys/{fn}",
                          "src": f"assets/series-src/MS_{code}_600.png",
                          "w": cell.width, "h": cell.height})
            slot += 1
    return slots


def main():
    result = {}
    for code in ROW_BANDS:
        slots = cut_series(code)
        result[code] = slots
        print(f"{code}: {len(slots)} 款 -> " +
              ", ".join(f"{s['slot']}.{s['name']}({s['w']}x{s['h']})" for s in slots))
    (ROOT / "data" / "slot_images.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    print("written data/slot_images.json")


if __name__ == "__main__":
    main()
