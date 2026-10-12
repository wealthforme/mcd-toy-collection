# 使用 WorkBuddy 开发的对话上下文

本项目「麦麦玩具收藏册」全程使用 WorkBuddy（麦当劳程序员创意开发大赛官方合作伙伴）开发。

## 开发过程

1. **MCP 接入**：在 WorkBuddy【专家·技能·连接器】→【连接器】→【自定义连接器】→【配置 MCP】中写入 `mcd-mcp`（`https://mcp.mcd.cn`，Bearer Token），完成连接并跑通 `tools/list`，实测拿到 35 个工具。

2. **能力勘探**：对全部只读工具做全量调用与对抗性审查，输出一份实测展示页，发现并修正了 9 类问题（HTTP 200 ≠ 业务成功、`calculate-price` 数量字段是 `quantity` 且金额单位为分、`mall-points-products` 需 `catRuleIds` 才能拿到积分类商品、`query-party-store` 门店编码字段是 `code`、`query-meals` 餐品列表在 `categories` 里而价格在 `meals` 映射里等）。

3. **选题确认**：在实测数据中检索「玩具」，发现 `query-meal-detail` 的 `rounds[]` 里带有**当前门店赠送的玩具**（海绵宝宝×航海王系列玩具，code 521991），且用玩具 code 再查一次即可拿到官方玩具图。官方文档并未说明这一点，遂定为项目核心。

4. **骨架搭建**：WorkBuddy 生成 `mcp_client.py`（Streamable HTTP 封装 + 业务状态解析）、`catalog.py`（玩具总库）、`scan_toys.py`（门店扫描 / 跨店比价）、`collection.py`（收藏册 CLI）、`build_web.py`（单文件收藏册页面），并补齐 `README.md`、`MCP_INTEGRATION.md`、`SKILL.md`、`CONTEST_DECLARATION.md`（官方原文未改动）、`.env.example`。

5. **真实数据验证**：实际跑通链路，当前库中共 6 款玩具（当前在售 2、历史款 2、积分兑换 2），全部拿到麦当劳官方图片。跨城扫描中在送的款（如成都的「随机玩具1个」）会被合并升级为「当前在售」，同时保留历史订单来源信息。

6. **跨城「找玩具」突破**：此前误判 `query-nearby-stores` 受账号限制只能返回一家门店；WorkBuddy 拉取 `tools/list` 的入参 schema 后逐组合验证，定位到真实原因是 `searchType=2` 时 **city 与 keyword 必须同时传**（缺任一返回 `600058`）。据此重写检索逻辑，用行政区关键词去重扩充门店池，完成 6 城 48 家门店扫描，产出 `data/availability.json`。

7. **图片真实性达标**：发现官方图床规则 `ProductPool/product/MS_<code>_600.png` 对已下市玩具同样返回 200，抽成 `mcp_client.guess_image()` 做 HEAD 校验补全，历史款全部换成官方真图，页面 9 张图校验 0 失败，占位图清零。

8. **按比赛规则补齐成品**：核对官方《活动规则》后补上 README 表格中未列出但规则要求的 `mcp-config.example.json`，并新增 `.gitignore`（隔离凭证与本地收藏状态）、`docs/architecture.svg` 架构图，完成 git 首次提交。

## WorkBuddy 承担的工作

- MCP 连接配置与连通性验证
- 接口返回结构的逆向与容错解析（Markdown / JSON / CSV 三种返回形态）
- 项目骨架与全部脚本的编写、调试、重跑
- 文档撰写、数据结构设计、架构图绘制、合规性自查

## 备注

- 全程未调用任何写操作工具（下单 / 领券 / 抽奖 / 建地址）
- 真实 Token 仅存于本地 `~/.workbuddy/mcp.json`，未写入任何项目文件
