# MCP 集成说明

本项目完全构建在**麦当劳中国 MCP Server**（`https://mcp.mcd.cn`，Streamable HTTP）之上。

- 传输：`streamablehttp`
- 鉴权：`Authorization: Bearer <MCP Token>`
- 限流：600 次/分钟（超限返回 429）
- 采集一次完整玩具库约需 10～20 次调用

## 使用的 Tool

| Tool | 用途 | 在本项目中的角色 |
|---|---|---|
| `query-nearby-stores` | 查询可点餐门店 | 取当前门店 `storeCode` |
| `query-meals` | 查询门店菜单 | 定位「开心乐园」分类，取乐园餐 `code` |
| `query-meal-detail` | 餐品详情 | **核心**：从套餐 `rounds` 中读出玩具选配轮；再用玩具 `code` 取官方图片 |
| `order-list` | 历史订单 | 递归解析 `orderProductList → comboItemList`，挖出历史玩具 |
| `mall-points-products` | 商城商品 | 取 `catName=玩具` 的积分兑换商品（`catRuleIds=2>8`） |
| `campaign-calendar` | 活动日历 | 提取含「玩具 / 乐园餐」的活动 |

未使用任何写操作工具：`create-order`、`cancel-order`、`mall-create-order`、`party-order-create`、`draw-lottery`、`auto-bind-coupons`、`delivery-create-address` 全部规避。

## 核心调用流程

```
当前热送
  query-nearby-stores{beType:1, searchType:1}
    └─> storeCode
        └─> query-meals{storeCode, orderType:1, beType:1}
            └─> categories[].meals[] 中 tags 含「开心乐园餐」的 code
                └─> query-meal-detail{storeCode, orderType:1, beType:1, code}
                    └─> rounds[] 中 name 含「玩具」的轮次 → choices[].code/name
                        └─> query-meal-detail{code: 玩具code} → image（官方玩具图）

历史款
  order-list{}
    └─> list[].orderProductList → 递归 comboItemList
        └─> name 含「玩具」的条目 → productCode
            └─> 图床规则 ProductPool/MS_<code>_600.png 补官方图，HEAD 校验 200 才采用

找玩具（跨城）
  scan_toys.py --per-city 8
    ├─ query-nearby-stores{beType:1, searchType:2, city:"深圳市", keyword:"南山"}
    │     ⚠ city 与 keyword 必须同时传，否则 600058；多关键词去重扩充门店池
    ├─ query-meals{storeCode}            营业校验（打烊返回 600057）
    └─ 对营业门店重复「当前热送」链路 → data/availability.json
```

## 业务价值

1. **官方接口未显式暴露的能力**：`query-meal-detail` 文档只写「查看套餐包含内容以及可以替换选项」，实际其 `rounds[]` 里带着**当前赠品玩具**的名称与 code——这是「今天送哪款玩具」的权威来源，比任何第三方攻略都准确。
2. **玩具图片可程序化获取**：把玩具 `code` 当餐品 code 再调一次 `query-meal-detail`，即可拿到 `menu-img.mcd.cn` 上的官方玩具图。
3. **收藏闭环**：`order-list` 能回溯历史玩具，`mall-points-products` 补充积分兑换款，两者与「当前在售」合并，构成有时间纵深的收藏册。点亮单位是**系列内单品**（每份乐园餐含随机玩具 1 个），系列卡展开成 6~10 个单品槽位逐款点亮，进度按单品累计。

## 实战踩坑（对开发者最有价值的部分）

| # | 坑 | 正解 |
|---|---|---|
| 1 | HTTP 200 不代表业务成功 | 必须解析返回文本中的 `"success"` / `"code"` / `"message"` |
| 2 | `query-meal-detail` 返回字段很精简 | 只有 `code / name / rounds / image / supportModify`，价格在 `query-meals` 的 `meals` 映射里 |
| 3 | 玩具图片要用玩具 code 再查一次 | 套餐 `rounds` 的 choices 里没有 image 字段 |
| 4 | 已下市玩具查不到详情 | `query-meal-detail` 返回业务失败/空，改按图床规则 `MS_<code>_600.png` HEAD 校验取官方图（见 #11），仍失败才用本地 SVG 占位 |
| 5 | `order-list` 商品字段是 `orderProductList` | 不是 `goods` / `productList`，套餐子项在 `comboItemList` |
| 6 | `campaign-calendar` 返回 Markdown 不是 JSON | 不能走 JSON 解析分支，需正则提取文本块 |
| 7 | `query-nearby-stores` 每次只回 1 家门店 | `searchType=1` 是「收藏餐厅」语义；换 `searchType=2` 且 **city + keyword 同时传**才能按城市召回，**缺任一都报 `600058`** |
| 8 | `mall-points-products` 不传 `catRuleIds` 返回现金类 | 积分类必须传 `catRuleIds=1>4`（商品券）/ `2>8`（周边） |
| 9 | 金额单位统一是「分」 | `calculate-price` 等接口返回的金额需 /100 |
| 10 | 非营业时段门店查不到菜单 | `query-meals` 返回 `600057 门店可能已关闭或不在营业时间`，扫描脚本需单独标记并跳过 |
| 11 | 历史玩具官方图拿不到 | 按图床规则 `ProductPool/product/MS_<code>_600.png` HEAD 校验补全，下市商品同样可用 |
| 12 | 商城周边只看 `catName=玩具` 会漏联名款 | Nike Book 2 麦当劳特别联名款 `catName` 是「鞋袜」，需按名称含「联名」补充收录 |
| 13 | 系列内单品拿不到 | `query-meal-detail` 只把整个系列作为一个选配项返回（试过玩具 code 直查、`mall-product-detail`、菜单搜索均无单品）；一套几款只能按官方系列图 `MS_<code>_600.png` 点数，单品名由用户自填 |
| 14 | 前端首行读写 localStorage 会整体挂掉 | 预览面板沙箱 iframe / 隐私模式下抛 `SecurityError`，整个脚本初始化即死；页签切换应改纯 CSS（`radio + :checked`），存储读写统一 try/catch 兜底 |
| 15 | 行内编辑依赖 blur 会丢输入 | input 未获焦时 `blur()` 不触发事件，Enter 必须直接提交，不能转手 blur |

## 凭证安全

代码不内置任何 Token。`MCD_MCP_TOKEN` 走环境变量或 `MCD_MCP_TOKEN_FILE`，`README.md` / `.env.example` 只出现占位符，符合参赛信息安全声明。
