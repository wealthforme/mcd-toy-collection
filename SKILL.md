---
name: mcd-toy-collection
description: 开心乐园餐玩具电子收藏册。当用户询问「麦当劳现在送什么玩具」「开心乐园餐玩具」「点亮/收藏玩具」「哪些店有哪款玩具」「玩具收藏册进度」时使用。基于麦当劳 MCP 查询当前门店赠品玩具（含官方图）、回溯历史订单里的玩具、按门店比价，并维护本地收藏册的点亮状态。
---

# 麦麦玩具收藏册

围绕**开心乐园餐赠品玩具**的收藏与查询工具，数据全部来自麦当劳官方 MCP。

## 环境

- Token：环境变量 `MCD_MCP_TOKEN`（或 `MCD_MCP_TOKEN_FILE`），未设置时回退读 `~/.workbuddy/mcp.json`
- 依赖：Python 3.9+ 标准库，无需 pip 安装
- 工作目录：`scripts/` 下的脚本可独立运行

## 能力

### 1. 查「当前送哪款玩具」

```bash
python scripts/catalog.py          # 重建玩具库（含当前在售 + 图片）
python scripts/build_web.py        # 生成收藏册页面
```

或只问当前门店热送：读 `data/toys.json` 中 `source == "current"` 的条目。

### 2. 收藏册点亮 / 进度（单品级）

每份开心乐园餐含**随机玩具 1 个**，拿到的是整套里的一款，所以点亮单位是系列内单品：

```bash
python scripts/collection.py list                                       # 总览：系列进度 + 每款明细
python scripts/collection.py collect <系列code> --slot <第几款> --name "<这款叫什么>" --store "<门店>"
python scripts/collection.py uncollect <系列code> --slot <第几款>
python scripts/collection.py rename <系列code> --slot <第几款> --name "<新名字>"
python scripts/collection.py add <系列code> --name "<拿到的款>"            # 随机玩具/超出预置款数时追加
python scripts/collection.py collect <单品code>                           # 非系列单品（积分周边）整体点亮
python scripts/collection.py stats
python scripts/collection.py sync
```

Web 收藏册（`web/index.html`）中：系列卡点芯片点亮/取消、点 `✎` 起名、点 `＋` 添加；积分周边卡点按钮整体点亮。状态存 localStorage。

系列单品数来自官方系列图点数（`catalog.py` 的 `LINEUP_COUNTS`），MCP 不提供系列内单品清单。

### 3. 找玩具（跨城门店扫描）

```bash
python scripts/scan_toys.py --per-city 8                      # 默认 6 城，每城 8 家
python scripts/scan_toys.py --cities 深圳市,广州市 --per-city 12
python scripts/scan_toys.py --stores 1420544,1420207          # 指定门店精准比对
```

输出玩具 × 门店可得性矩阵 → `data/availability.json`，`web/index.html` 的「找玩具」页读取它。

门店检索要求：`searchType=2` 且 **city + keyword 同时传**（缺一报 `600058`）；
非营业时段门店在 `query-meals` 返回 `600057`，标记为不可点餐并跳过。

## 数据说明

- 玩具图片一律为官方图：在售款取 `query-meal-detail` 的 `image`；下市款按图床规则
  `https://menu-img.mcd.cn/pcm/prod/menu/ProductPool/product/MS_<code>_600.png` 校验补全；
  积分周边取 `mall-points-products` 的 `spuImage`
- 「当前在售」来自套餐 `rounds` 中名称含「玩具」的选配轮
- 收藏册按「当前在送 / 历史款（订单里拿到过的）/ 积分兑换周边」三组呈现，历史款卡片标注下单日期
- 页面包含三块：当前热送大卡、可点亮的电子收藏册、按城市/营业状态筛选的门店清单
- 三个页签为 `radio + :checked` 纯 CSS 切换，不依赖 JS；localStorage 不可用时自动降级为内存态，
  点亮、筛选、导出仍可用

## 已知限制

- 单次门店检索最多约 5 家，靠多行政区关键词去重扩充，仍是抽样
- 非营业时段可用性覆盖率下降（实测夜间 48 家中 17 家可点餐），白天重跑更完整
- 当期玩具配送偏全国统一，跨店差异主要体现在门店距离与营业状态

## 不要用

不要调用 `create-order`、`auto-bind-coupons`、`draw-lottery`、`mall-create-order` 等写操作工具——本 Skill 只做只读查询与本地记录。
