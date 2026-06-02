# Recipe 驱动 PPT 生成方案

## 一、什么是 Recipe

Recipe（配方）就是把"PPT 该长什么样"用一份 JSON 文件预先定义好。AI 不再自主决定页数、顺序、类型，而是严格按 Recipe 逐章逐页执行。

**类比：**

```
ReAct        = 让厨师即兴发挥做一桌菜
Plan-Execute = 厨师先写菜单再做菜
Recipe       = 你给厨师一张固定菜谱，他只负责按菜谱切菜下锅
```

## 二、为什么 PPT 场景特别适合 Recipe

一份运维/财务报告 PPT 的结构非常固定：

```
报表每月重复生成，变得只是数据，结构不变
  ├── 封面（标题、日期、作者）
  ├── 目录
  ├── 第1章 CPU分析
  │     ├── KPI概览（3个指标卡片）
  │     ├── 趋势图（7天曲线）
  │     ├── 异常明细表
  │     └── 文字分析
  ├── 第2章 内存分析
  │     └── 和CPU分析一模一样，只是指标不同
  ├── ...
  └── 总结
```

Recipe 把这个结构固化下来，**变化的部分（数据）和不变的部分（结构）彻底分离**。

## 三、Recipe JSON 结构

### 3.1 顶层结构

```json
{
  "name": "月度运维分析报告",
  "version": "1.0",
  "template": "mcp_servers/templates/default.pptx",
  "chapters": [
    { "title": "一、整体概览",   "pages": [...] },
    { "title": "二、CPU分析",    "pages": [...] },
    { "title": "三、内存分析",   "pages": [...] }
  ]
}
```

### 3.2 每一页的定义

```json
{
  "type": "cover",
  "data": {
    "title": "{{report_name}}",
    "subtitle": "{{date}}",
    "author": "AI自动生成"
  }
}
```

```json
{
  "type": "kpi_overview",
  "title": "核心指标概览",
  "data": {
    "metrics": [
      { "name": "CPU使用率", "value": "{{sql: SELECT AVG(usage) FROM cpu_metrics WHERE date='this_week'}}", "unit": "%", "threshold": 80 },
      { "name": "内存使用率", "value": "{{sql: SELECT AVG(usage) FROM mem_metrics WHERE date='this_week'}}", "unit": "%", "threshold": 90 }
    ]
  }
}
```

```json
{
  "type": "data_table",
  "title": "CPU告警明细",
  "data": {
    "columns": ["时间", "主机", "告警等级", "详情"],
    "sql": "SELECT time, host, level, detail FROM alerts WHERE type='cpu' AND date='this_week' ORDER BY time DESC LIMIT 50"
  }
}
```

```json
{
  "type": "text_summary",
  "title": "CPU分析总结",
  "data": {
    "rag_query": "CPU使用率过高排查方法与优化建议",
    "max_bullets": 5
  }
}
```

### 3.3 变量替换机制

Recipe 支持三种占位符，AI 在生成前自动解析：

| 占位符格式 | 说明 | 示例 |
|-----------|------|------|
| `{{date}}` | 当前日期 | `2026-06-02` |
| `{{report_name}}` | 报告名称（从 Recipe 继承） | `月度运维分析报告` |
| `{{sql: ...}}` | SQL 查询 → 自动调 db_server | `SELECT AVG(usage)...` |
| `{{rag: ...}}` | 知识检索 → 自动调 RAG | `CPU过高排查方法` |

## 四、执行流程

```
用户: "生成本月运维报告"

Recipe Engine:
  │
  ├─ 1. 加载 recipe.json → 解析出 3 章 15 页
  │
  ├─ 2. 第1章
  │     ├─ 封面页 → 替换 {{date}} → ppt_server.create_presentation
  │     ├─ KPI页  → 替换 {{sql:...}} → db_server.execute_query → ppt_server.add_chart
  │     ├─ 表格页 → 替换 {{sql:...}} → db_server.execute_query → ppt_server.add_table
  │     └─ 总结页 → 替换 {{rag:...}} → RAG检索 → ppt_server.add_content
  │     → 第1章完成 ✅，保存中间文件 chapter_1.pptx
  │
  ├─ 3. 第2章
  │     └─ ... 和第1章同样的流程 ...
  │     → 第2章完成 ✅，保存 chapter_2.pptx
  │
  ├─ 4. 第3章 → ... → chapter_3.pptx
  │
  └─ 5. 合并所有 chapter_*.pptx → 生成目录 → 最终输出.pptx
```

关键设计：**每章独立执行、独立保存**。第 3 章失败不影响第 1、2 章，只需重做第 3 章。

## 五、与 ReAct / Plan-Execute 的核心区别

| | ReAct | Plan-Execute | Recipe |
|---|---|---|---|
| **谁决定结构** | AI 自由发挥 | AI 临时规划 | 人类预先定义 |
| **可预测性** | 低（每次不同） | 中（规划可能偏差） | 高（每次一致） |
| **200 页可靠性** | ❌ 不可能 | ❌ 超长规划不可靠 | ✅ 分章节逐个击破 |
| **断点续传** | ❌ | ❌ | ✅ 每章独立 |
| **修改单页** | 全部重来 | 全部重来 | 只改那页的 Recipe |
| **Token 消耗** | 高（上下文堆积） | 中 | 低（每章独立上下文） |
| **首次配置成本** | 零 | 零 | 需要写 Recipe JSON |

## 六、Recipe 从哪来

### 6.1 手动编写（MVP 阶段）

人工分析原始 200 页 PPT，抽象页面类型，手写 JSON：

```
原始PPT                           Recipe定义
─────────────────────────        ────────────────
封面（蓝底白字，标题居中）    →   { "type": "cover" }
KPI页（3个圆环图+指标）       →   { "type": "kpi_overview", "metrics": [...] }
趋势图（折线图，7天数据）    →   { "type": "trend_chart", "sql": "..." }
明细表（10列，分页）          →   { "type": "data_table", "sql": "..." }
文字总结（要点+结论）         →   { "type": "text_summary", "rag_query": "..." }
```

一份 200 页的 PPT，最终就是 6-7 种页面类型循环几十次。Recipe JSON 可能只有 200 行。

### 6.2 AI 辅助生成（进阶）

给 AI 一份原始 PPT，让它分析结构并生成 Recipe JSON：

```
"分析这份PPT的结构，输出为 Recipe JSON。识别出重复的页面模式，
每种模式定义一个 type，统计每种 type 出现多少次。"
```

### 6.3 从数据库 Schema 自动生成（终极）

根据数据库表结构 + RAG 知识库中的运维规范，自动推断"应该有哪些指标、哪些图表"：

```
metrics 表有哪些字段 → 每个字段一个 KPI 卡
alerts 表有哪些告警类型 → 每种类型一个异常明细表
RAG 中记录了哪些检查项 → 每项一个总结页
```

## 七、页面类型库（标准的 7 种）

| type | 说明 | 输入数据 |
|------|------|---------|
| `cover` | 封面页 | title, subtitle, date |
| `toc` | 目录页 | chapter_titles: list |
| `kpi_overview` | 指标卡片（3-4个并排） | metrics: [{name, value, unit}] |
| `trend_chart` | 趋势折线图/柱状图 | sql → [{date, value}] |
| `data_table` | 数据明细表 | sql → columns + rows |
| `anomaly_list` | 异常/告警列表 | sql → [{time, level, detail}] |
| `text_summary` | 文字分析总结 | rag_query + max_bullets |

这 7 种类型覆盖了 90% 的运维报告页面。如果出现新类型，加一种即可——不改架构，只加一个渲染函数。

## 八、开发步骤

| 阶段 | 内容 | 产出 |
|:--:|------|------|
| 1 | 定义 Recipe Schema（JSON 格式规范） | `recipe_schema.md` |
| 2 | 分析你的 200 页原始 PPT → 手写第一版 Recipe | `recipes/monthly_report.json` |
| 3 | 实现 Recipe Engine（解析 + 执行 + 章节管理） | `app/services/recipe_engine.py` |
| 4 | 接入现有 ppt_server / db_server / RAG 工具 | 不改工具，Engine 调工具 |
| 5 | 加 API 路由 + 前端入口 | `/api/recipe/run` |
| 6 | 逐步从手动 Recipe → AI 辅助生成 Recipe | 迭代优化 |

## 九、与现有架构的关系

```
                      ┌─────────────────────┐
                      │    Recipe Engine     │  ← 新增
                      │  加载/解析/执行Recipe │
                      └──────────┬──────────┘
                                 │ 调用
              ┌──────────────────┼──────────────────┐
              ▼                  ▼                  ▼
     ┌────────────┐    ┌────────────┐    ┌────────────┐
     │ RAG 检索    │    │ db_server  │    │ ppt_server │
     │ (已有)      │    │ (已有)      │    │ (已有)      │
     └────────────┘    └────────────┘    └────────────┘
```

Recipe Engine 是**编排层**，不是替代层。它会调用现有的三个 MCP Server，自己不做知识检索、不写 SQL、不渲染 PPT——这些仍然是现有工具的事。

## 十、总结

> Recipe 的本质：**把"每次生成都要 AI 重新思考一遍的结构"固化下来，AI 只做它擅长的事——理解语义、组织文字、查询数据。**
