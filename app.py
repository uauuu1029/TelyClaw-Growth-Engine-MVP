"""TelyClaw Growth Engine — Flask MVP with window-aware mock trend data."""

from copy import deepcopy
from datetime import datetime, timezone
import re
from uuid import uuid4

from flask import Flask, jsonify, render_template, request

app = Flask(__name__)

WORKSPACE = {
    "name": "TelyClaw 增长引擎",
    "last_sync": "刚刚同步",
    "sync_interval": "每 4 小时自动更新",
    "next_sync": "实时同步中…",
}

NORTH_STAR_METRIC = {
    "name": "Avg. Qualified Engagement / Post",
    "label": "单篇热点推文平均有效互动",
    "value": 1240,
    "trend_percent": 18,
    "comparison_label": "较上周",
    "period_label": "最近 7 天已批准并发布的热点内容",
    "breakdown": [
        {"key": "replies", "label": "回复", "value": 320, "icon": "message-circle"},
        {"key": "reposts", "label": "转发", "value": 230, "icon": "repeat-2"},
        {"key": "bookmarks", "label": "收藏", "value": 280, "icon": "bookmark"},
        {"key": "profile_visits", "label": "主页访问", "value": 260, "icon": "user-round"},
        {"key": "product_clicks", "label": "产品点击", "value": 150, "icon": "mouse-pointer-click"},
    ],
}

SUPPORTING_METRICS = [
    {
        "name": "Trend Detection Lead Time",
        "label": "热点发现提前量",
        "value": "2.5 小时",
        "context": "平均比全网舆情爆发提前发现",
        "icon": "radar",
    },
    {
        "name": "Trend to Content Time",
        "label": "热点到内容的转化时长",
        "value": "4.2 分钟",
        "context": "极速生成，优于 < 5-10 min 的设定目标",
        "icon": "timer",
    },
    {
        "name": "Trend Hit Rate",
        "label": "热点命中率",
        "value": "92%",
        "context": "Top Trends 中真正被确认值得参与的比例",
        "icon": "crosshair",
    },
    {
        "name": "Content Acceptance Rate",
        "label": "内容直接采用率",
        "value": "85%",
        "context": "AI 生成草稿无需大幅修改即可发布的比例",
        "icon": "circle-check-big",
    },
    {
        "name": "Engagement Lift",
        "label": "互动提升率",
        "value": "+315%",
        "context": "相对常规普通内容的额外 Engagement 增长",
        "icon": "chart-no-axes-combined",
    },
    {
        "name": "Qualified Engagement",
        "label": "有效互动总量",
        "value": "12.4k",
        "suffix": "/ 月",
        "context": "由系统趋势内容带来的总体高质量互动",
        "icon": "mouse-pointer-click",
    },
]

MOCK_ACCOUNTS = [
    {"id": "openai", "name": "OpenAI", "handle": "@OpenAI", "followers": "4.1M", "initials": "OA", "color": "#111827", "status": "active", "niche_tags": ["#AI", "#Research"], "posts_24h": 18, "last_active": "12 分钟前"},
    {"id": "sama", "name": "Sam Altman", "handle": "@sama", "followers": "3.4M", "initials": "SA", "color": "#2563EB", "status": "active", "niche_tags": ["#AI", "#Founder"], "posts_24h": 12, "last_active": "35 分钟前"},
    {"id": "ycombinator", "name": "Y Combinator", "handle": "@ycombinator", "followers": "1.4M", "initials": "YC", "color": "#F97316", "status": "active", "niche_tags": ["#SaaS", "#Startup"], "posts_24h": 16, "last_active": "48 分钟前"},
    {"id": "levelsio", "name": "Pieter Levels", "handle": "@levelsio", "followers": "592K", "initials": "PL", "color": "#7C3AED", "status": "active", "niche_tags": ["#IndieHacker", "#SaaS"], "posts_24h": 9, "last_active": "2 小时前"},
    {"id": "karpathy", "name": "Andrej Karpathy", "handle": "@karpathy", "followers": "1.3M", "initials": "AK", "color": "#0F766E", "status": "active", "niche_tags": ["#AI", "#Developer"], "posts_24h": 7, "last_active": "1 小时前"},
    {"id": "paulg", "name": "Paul Graham", "handle": "@paulg", "followers": "2.0M", "initials": "PG", "color": "#BE123C", "status": "active", "niche_tags": ["#Founder", "#Startups"], "posts_24h": 5, "last_active": "3 小时前"},
]

ACCOUNT_COLORS = ["#076B4D", "#2563EB", "#7C3AED", "#C2410C", "#BE123C", "#0F766E"]

SYNC_ACTIVITY = [
    {"id": "sync-1", "time": "10 分钟前", "lead": "成功扫描了", "account": "@sama", "message": "的 3 条最新推文", "icon": "circle-check", "tone": "success"},
    {"id": "sync-2", "time": "45 分钟前", "lead": "从", "account": "@ycombinator", "message": "提取了 1 个潜力关键词：Browser-native", "icon": "scan-search", "tone": "signal"},
    {"id": "sync-3", "time": "2 小时前", "lead": "", "account": "@levelsio", "message": "触发了互动量阈值警告（Engagement Spike）", "icon": "chart-no-axes-combined", "tone": "alert"},
    {"id": "sync-4", "time": "3 小时前", "lead": "已完成", "account": "@OpenAI", "message": "的新一轮 4 小时窗口同步，共聚类 2 个 Topics", "icon": "refresh-cw", "tone": "success"},
    {"id": "sync-5", "time": "4 小时前", "lead": "从", "account": "@karpathy", "message": "的 7 条帖子中识别出 Agent Memory 上升信号", "icon": "sparkles", "tone": "signal"},
]

WINDOW_LABELS = {
    "1h": "最近1小时内",
    "4h": "最近4小时内",
    "24h": "最近24小时内",
    "3d": "最近三天内",
    "7d": "最近七天内",
}


def angle(title, description):
    return {"title": title, "description": description}


def build_source_posts(trend_id, topic, summary, source, velocity, source_post_count):
    """Create a small evidence sample behind each aggregate mock trend."""
    handles = [item.strip() for item in source.split("·") if item.strip()]
    if not handles:
        handles = ["@telyclaw_signal"]
    display_names = {
        "@OpenAI": "OpenAI",
        "@sama": "Sam Altman",
        "@karpathy": "Andrej Karpathy",
        "@ycombinator": "Y Combinator",
        "@levelsio": "Pieter Levels",
        "@paulg": "Paul Graham",
        "@swyx": "Swyx",
    }
    window_key = trend_id.split("-", 1)[0]
    time_labels = {
        "1h": ["8 分钟前", "19 分钟前", "37 分钟前", "52 分钟前"],
        "4h": ["18 分钟前", "47 分钟前", "2 小时前", "3 小时前"],
        "24h": ["1 小时前", "5 小时前", "11 小时前", "19 小时前"],
        "3d": ["4 小时前", "昨天", "2 天前", "3 天前"],
        "7d": ["8 小时前", "2 天前", "4 天前", "6 天前"],
    }.get(window_key, ["刚刚", "1 小时前", "2 小时前", "3 小时前"])
    post_texts = [
        f"我们正在看到『{topic}』从零散讨论变成明确共识。{summary}",
        f"一个被低估的信号：『{topic}』相关讨论增速已经达到 {velocity}，但真正可复用的实操框架仍然稀缺。",
        f"团队现在不该只问这个趋势有多热，而要问它会重写哪段工作流。『{topic}』正在把这个问题推到台前。",
        f"抽样查看近期 {source_post_count} 条相关帖子后，最明显的变化不是声量，而是从概念讨论转向真实落地与结果验证。",
    ]
    colors = ["#111827", "#2563EB", "#7C3AED", "#0F766E"]
    posts = []
    for index, text in enumerate(post_texts):
        handle = handles[index % len(handles)]
        username = display_names.get(handle, handle.lstrip("@").replace("_", " ").title())
        initials = "".join(part[0] for part in username.split()[:2]).upper() or "X"
        posts.append({
            "id": f"{trend_id}-source-{index + 1}",
            "avatar": initials,
            "avatar_color": colors[index % len(colors)],
            "username": username,
            "handle": handle,
            "text": text,
            "posted_at": time_labels[index],
        })
    return posts


# TelyClaw Opportunity Score is deliberately not a popularity score.
# Brand relevance receives the highest weight so large but commercially irrelevant
# conversations cannot outrank smaller signals that TelyClaw can credibly own.
OPPORTUNITY_WEIGHTS = {
    "velocity": 0.30,
    "relevance": 0.50,
    "content_opportunity": 0.20,
}


def calculate_opportunity_score(factors):
    return round(sum(factors[key] * weight for key, weight in OPPORTUNITY_WEIGHTS.items()))


def make_trend(
    trend_id,
    topic,
    summary,
    score,
    heat,
    heat_level,
    velocity,
    mentions,
    source,
    source_post_count,
    ranking_reason,
    visual_title,
    visual_stat,
    visual_caption,
    copy,
    tags,
    content_angles,
    score_factors=None,
):
    score_factors = score_factors or {
        "velocity": min(99, score + 2),
        "relevance": score,
        "content_opportunity": max(70, score - 2),
    }
    score = calculate_opportunity_score(score_factors)
    source_posts = build_source_posts(
        trend_id, topic, summary, source, velocity, source_post_count
    )
    angle_schema = [
        ("Hot Take / Opinion", "犀利观点"),
        ("Educational / Insight", "深度科普"),
        ("TelyClaw Product Angle", "产品结合点"),
    ]
    normalized_angles = []
    for index, (category, label_cn) in enumerate(angle_schema):
        original = content_angles[index]
        normalized_angles.append({
            "title": category,
            "label_cn": label_cn,
            "focus": original["title"],
            "description": original["description"],
        })
    content_angles = normalized_angles
    if not all(dimension in ranking_reason for dimension in ("传播爆发力", "品牌契合度", "内容机会")):
        ranking_reason = (
            f"推荐理由：{ranking_reason}，信号仍处于上升窗口（传播爆发力）。"
            f"议题可自然连接 TelyClaw 的 AI 工作流与增长自动化能力（品牌契合度）。"
            f"现有讨论尚未形成系统化解法，仍有输出原创框架的空间（内容机会）。"
        )
    floor = max(12, score - 68)
    chart = [floor, floor + 5, floor + 3, floor + 14, floor + 20, score - 25, score - 16, score - 8, score]
    drafts = [
        {
            "id": "A",
            "label": "草稿 A",
            "style": "数据驱动",
            "text": (
                f"过去几小时，「{topic}」越过了普通热点的边界。相关讨论增速达到 {velocity}，"
                f"我们已分析 {source_post_count} 条来源帖，市场认知正在加速收敛。\n\n"
                f"在 TelyClaw 的模型里，{score} 分不等于“立即跟风”。{summary}"
                f"真正的窗口，是需求抬升、答案尚未成为共识的片刻。\n\n"
                f"{content_angles[0]['description']}先发优势不是抢到第一个热词，"
                f"而是更早给出理解问题的框架。数据只是入口，判断才是护城河。"
            ),
        },
        {
            "id": "B",
            "label": "草稿 B",
            "style": "痛点反转",
            "text": (
                f"「{topic}」的讨论增速已来到 {velocity}。但 {source_post_count} 条相关帖子暴露出的，"
                f"不是功能渴望，而是用户对摩擦越来越不耐烦。\n\n"
                f"TelyClaw 追问热度背后的“未完成任务”。{summary}"
                f"大众看到能力，增长团队该看到旧工作流已承受不了新预期。\n\n"
                f"{content_angles[1]['description']}机会不在复述趋势，而在重写任务路径。"
                f"当多数品牌还在解释现象，赢家已经在追问：哪个动作可以彻底消失？"
            ),
        },
        {
            "id": "C",
            "label": "草稿 C",
            "style": "创始人视角",
            "text": (
                f"这周，创始人和产品团队反复讨论「{topic}」。{summary}"
                f"表面是能力跃迁，实质却在重划机器与人的责任边界。\n\n"
                f"TelyClaw 的选择是：系统分析 {source_post_count} 条信号、比较叙事并完成初稿，"
                f"人保留品牌语气、事实判断和发布权。速度可以自动化，立场不能。\n\n"
                f"{content_angles[2]['description']}未来内容团队的护城河不是产量，"
                f"而是把机器速度、人类判断和数据，组合成持续进化的增长工作流。"
            ),
        },
    ]
    return {
        "id": trend_id,
        "topic": topic,
        "summary": summary,
        "score": score,
        "score_dimensions": score_factors,
        "velocity_score": score_factors["velocity"],
        "relevance_score": score_factors["relevance"],
        "opportunity_score": score_factors["content_opportunity"],
        "engagement_score": min(99, round((score_factors["velocity"] + score_factors["content_opportunity"]) / 2)),
        "independent_accounts_count": max(len({post["handle"] for post in source_posts}), round(score / 7)),
        "freshness_index": min(99, score_factors["velocity"] + 1),
        "score_formula": "传播爆发力 30% + TelyClaw 品牌契合度 50% + 内容机会 20%",
        "heat": heat,
        "heat_level": heat_level,
        "velocity": velocity,
        "mentions": mentions,
        "source": source,
        "source_post_count": source_post_count,
        "source_posts": source_posts,
        "ranking_reason": ranking_reason,
        "chart": chart,
        "visual_title": visual_title,
        "visual_stat": visual_stat,
        "visual_caption": visual_caption,
        "copy": copy,
        "tags": tags,
        "content_angles": content_angles,
        "drafts": drafts,
    }


TREND_SETS = {
    "1h": [
        make_trend(
            "1h-voice-agents", "Voice Agents 突破实时延迟临界点", "新一代语音智能体将端到端响应压缩至接近真人对话水平。",
            98, "急速爆发", "surging", "+246%", "3.9K", "@OpenAI · @sama", 84,
            "过去 60 分钟内被 4 个头部 AI 账号集中提及，转发速度达到基线的 3.4 倍。",
            "VOICE BECOMES THE INTERFACE", "320ms", "端到端响应延迟",
            "AI 的下一代界面，可能不是一个更聪明的聊天框。\n\n而是一段不需要等待的实时对话。\n\n当语音 Agent 的响应延迟接近人类交流节奏，客服、销售和陪伴型产品都会被重新设计。\n\n真正的拐点不是“能说话”，而是“对话不再让人出戏”。",
            ["#VoiceAI", "#AIAgents", "#Realtime"],
            [angle("数据驱动", "用 320ms 延迟数据解释实时语音为何跨过可用性门槛。"), angle("体验反转", "从用户讨厌等待切入，强调自然对话的产品体验。"), angle("行业预测", "预测客服、销售与陪伴产品将首先被重构。")],
            score_factors={"velocity": 99, "relevance": 92, "content_opportunity": 88},
        ),
        make_trend(
            "1h-browser-agents", "Browser-native Agents 开始代替重复操作", "浏览器内智能体从演示进入可复用的真实任务执行。",
            91, "高热度", "hot", "+132%", "2.6K", "@karpathy · @ycombinator", 67,
            "1 小时内相关演示帖保存率提升 89%，开发者讨论集中在稳定性和可观察性。",
            "THE BROWSER CAN ACT", "2.8×", "任务完成帖互动率",
            "浏览器正在从信息入口，变成 Agent 的工作台。\n\n真正有价值的不是自动点击，而是能理解目标、处理中断，并把关键决定交还给人。\n\n下一批 AI 产品，会更像同事，而不是快捷键。",
            ["#BrowserAgents", "#Automation", "#FutureOfWork"],
            [angle("工作流拆解", "展示 Agent 如何把多步网页操作压缩为一次委派。"), angle("风险边界", "讨论自动化执行中权限、确认与审计的重要性。"), angle("产品机会", "列举最适合 Browser Agent 的三个高频场景。")],
            score_factors={"velocity": 94, "relevance": 98, "content_opportunity": 91},
        ),
        make_trend(
            "1h-context-memory", "Long-term Memory 成为 Agent 新战场", "持续记忆让 Agent 从一次性工具转向长期协作伙伴。",
            83, "快速升温", "rising", "+76%", "1.7K", "@sama · @paulg", 42,
            "讨论量在 45 分钟内翻倍，用户对隐私控制和记忆准确性的互动最强。",
            "MEMORY CHANGES THE PRODUCT", "2.1×", "记忆功能讨论增速",
            "当 AI 记得你的偏好、项目和上一次决定，产品关系就发生了变化。\n\n但记忆越强，用户越需要看得见、改得掉、随时能清空。\n\n长期记忆的护城河，最终会是信任。",
            ["#AIMemory", "#Agents", "#Privacy"],
            [angle("信任视角", "把记忆能力与用户控制权放在同一框架讨论。"), angle("产品设计", "提出可查看、可编辑、可清空的记忆 UX 原则。"), angle("长期关系", "解释记忆如何改变 SaaS 留存与用户关系。")],
            score_factors={"velocity": 86, "relevance": 89, "content_opportunity": 99},
        ),
    ],
    "4h": [
        make_trend(
            "4h-agent-hallucination", "Agentic Workflows 的真正瓶颈：幻觉正在污染执行链", "团队开始发现，Agent 能连续执行并不等于结果可靠；一次错误会沿多步骤工作流被放大。",
            98, "强烈爆发", "surging", "+231%", "18.6K", "@OpenAI · @karpathy · @swyx", 214,
            "推荐理由：过去 4 小时由 15 个独立头部账号集中引爆，讨论增速达 231%（传播爆发力）。问题直接命中 TelyClaw『AI 重构工作流 + 人工终审』的核心定位（品牌契合度）。现有内容多停留在模型能力争论，缺少可验证、可回滚的执行链方案，实操洞察存在明显供给缺口（内容机会）。",
            "AUTOMATION WITHOUT TRUST BREAKS", "7.4×", "错误在多步执行链中的放大倍数",
            "Agent 能完成任务，不代表它能承担结果。\n\n真正危险的幻觉不是一句答错，而是错误被下一个工具当成事实继续执行。\n\n工作流的下一场竞争，不是更长的自动化链，而是谁先把验证、回滚与人工审批做成默认能力。",
            ["#AgenticWorkflows", "#AIEvals", "#HumanInTheLoop"],
            [angle("失控成本", "拆解一次幻觉如何在多步骤 Agent 链中被连续放大。"), angle("工作流重构", "用验证点、回滚和人工批准重新定义可靠自动化。"), angle("产品判断", "指出下一代 Agent 护城河将从执行速度转向可控性。")],
            score_factors={"velocity": 97, "relevance": 99, "content_opportunity": 95},
        ),
        make_trend(
            "4h-founder-content-bottleneck", "Founder-led Content 的隐形瓶颈：创始人正在被运营拖垮", "创始人内容拥有更高信任，却被选题、追踪趋势、改稿和发布节奏消耗了最稀缺的决策时间。",
            96, "高速上升", "surging", "+176%", "14.2K", "@levelsio · @paulg · @ycombinator", 188,
            "推荐理由：4 小时内 11 位 SaaS 创始人的运营复盘形成密集传播，相关帖收藏率提升 168%（传播爆发力）。其痛点与 TelyClaw『自动捕捉趋势、生成候选内容、保留创始人判断』高度同构（品牌契合度）。行业仍把 Founder-led Content 解释为个人勤奋，自动化运营系统的讨论严重不足（内容机会）。",
            "THE FOUNDER IS NOT A CONTENT OPS TEAM", "62%", "创始人时间耗在内容运营环节",
            "创始人 IP 的瓶颈从来不是没有观点，而是观点被运营流程吞掉。\n\n选题、资料整理和初稿可以自动化，但立场与最终判断必须保留。\n\n最有效的系统不是替创始人说话，而是把他的注意力还给真正值得表达的那一刻。",
            ["#FounderLedContent", "#BuildInPublic", "#GrowthAutomation"],
            [angle("时间账单", "量化创始人在选题、搜集和改稿上的隐性运营成本。"), angle("自动化边界", "拆分机器可代劳的执行与创始人必须保留的判断。"), angle("增长系统", "把个人持续输出升级为可复盘的品牌增长工作流。")],
            score_factors={"velocity": 90, "relevance": 99, "content_opportunity": 97},
        ),
        make_trend(
            "4h-content-sameness", "AI 内容同质化正在制造新的流量内卷", "生成门槛下降后，社交媒体充斥结构相同、立场缺失的内容；发布量增长，真实注意力却进一步稀释。",
            94, "高转化机会", "hot", "+143%", "11.7K", "@swyx · @levelsio · @paulg", 171,
            "推荐理由：反 AI 味内容在过去 4 小时获得 143% 互动增量，并被 9 个增长类头部账号交叉引用（传播爆发力）。它直接关联 TelyClaw『趋势筛选 + 原创视角 + 人工审核』的差异化价值（品牌契合度）。市场批评集中在“AI 写得像 AI”，但鲜少有人提出从信号、立场到审核的系统解法（内容机会）。",
            "MORE CONTENT. LESS ATTENTION.", "−38%", "同质化内容平均互动深度",
            "AI 让内容生产变便宜，也让平庸内容变得无限供应。\n\n真正稀缺的已不是文字，而是值得被记住的判断。\n\n下一轮内容竞争不会奖励发布最多的人，而会奖励能从同一趋势中提出不同结论、并为结论负责的品牌。",
            ["#AIContent", "#ContentStrategy", "#AttentionEconomy"],
            [angle("注意力稀释", "用发布量上升、互动深度下降揭示内容供给过剩。"), angle("反同质化", "说明原创立场为何比更流畅的生成文案更稀缺。"), angle("系统解法", "从趋势选择、观点生成到人工审核构建差异化闭环。")],
            score_factors={"velocity": 92, "relevance": 94, "content_opportunity": 99},
        ),
    ],
    "24h": [
        make_trend(
            "24h-coding-delegation", "AI Coding 从补全走向任务委派", "开发团队开始把完整 Issue 而不只是代码片段交给 Coding Agent。",
            94, "全天热门", "surging", "+148%", "31.2K", "@karpathy · @ycombinator", 428,
            "过去 24 小时出现 11 个高互动实战案例，完整任务委派相关内容占讨论增量的 63%。",
            "DELEGATE THE ISSUE", "63%", "讨论增量来自任务委派",
            "AI Coding 的真正拐点，不是补全更快。\n\n而是你可以交出一个 Issue，等待一个经过验证的结果。\n\n从 autocomplete 到 delegation，工程师的核心能力也从写每一行代码，变成定义问题与验收结果。",
            ["#CodingAgents", "#DeveloperTools", "#Engineering"],
            [angle("角色变化", "讨论工程师从编码者到任务设计与验收者的转变。"), angle("效率数据", "用完整 Issue 委派案例量化节省的开发时间。"), angle("实践指南", "给出适合委派给 Coding Agent 的任务清单。")],
            score_factors={"velocity": 98, "relevance": 91, "content_opportunity": 88},
        ),
        make_trend(
            "24h-mcp-ecosystem", "MCP 正在成为 AI 工具连接层", "标准化工具协议让 Agent 接入企业数据和业务系统的成本下降。",
            88, "高热度", "hot", "+86%", "22.7K", "@OpenAI · @sama", 336,
            "24 小时内新增 38 个连接器项目，开发教程的保存率是普通 AI 帖子的 2.9 倍。",
            "ONE PROTOCOL. MORE TOOLS.", "38", "新增连接器项目",
            "Agent 的能力上限，不只取决于模型。\n\n它还取决于能否安全、稳定地连接真实工具。\n\n当连接协议标准化，团队终于可以把精力从重复集成，转回真正的业务工作流。",
            ["#MCP", "#AIAgents", "#DeveloperExperience"],
            [angle("生态数据", "从 38 个新连接器展示协议网络效应。"), angle("开发痛点", "解释标准协议如何减少重复集成工作。"), angle("企业落地", "聚焦权限、审计和内部系统连接。")],
            score_factors={"velocity": 90, "relevance": 99, "content_opportunity": 93},
        ),
        make_trend(
            "24h-ai-evals", "Evals 成为 AI 产品的新 CI", "团队用持续评测替代发布前的主观试玩。",
            81, "稳定上升", "steady", "+49%", "14.5K", "@OpenAI · @karpathy", 219,
            "评测框架相关帖子中，带失败案例的内容平均获得 71% 更高互动。",
            "EVALS ARE THE NEW CI", "+71%", "失败案例内容互动提升",
            "没有 Evals 的 AI 产品，就像没有测试的代码。\n\nDemo 可以证明它偶尔有效；持续评测才能证明它在真实边界条件下依然可靠。\n\n把失败样本变成发布门槛，才是可持续的 AI 迭代。",
            ["#AIEvals", "#LLMOps", "#ProductQuality"],
            [angle("工程类比", "用 CI/CD 类比解释持续评测的必要性。"), angle("失败样本", "强调从真实失败中建立评测集。"), angle("落地清单", "给团队一套最小可用 Evals 流程。")],
            score_factors={"velocity": 82, "relevance": 86, "content_opportunity": 100},
        ),
    ],
    "3d": [
        make_trend(
            "3d-founder-distribution", "Founder-led Distribution 取代单一品牌投放", "连续三天的数据表明，创始人内容正在成为早期 SaaS 的主要自然增长渠道。",
            92, "三日领跑", "surging", "+116%", "58.4K", "@levelsio · @paulg", 782,
            "过去三天 7 位头部创始人的复盘帖持续进入热门，平均互动率是品牌账号的 4.1 倍。",
            "FOUNDERS OWN DISTRIBUTION", "4.1×", "创始人帖平均互动率",
            "早期产品最稀缺的，往往不是功能，而是可信的分发。\n\n创始人亲自解释问题、取舍和结果，正在成为品牌无法复制的增长渠道。\n\nDistribution is becoming a founder skill. 不只是市场团队的任务。",
            ["#FounderLedGrowth", "#Distribution", "#SaaS"],
            [angle("数据论证", "对比创始人与品牌账号的三日互动表现。"), angle("能力模型", "把分发重新定义为创始人的核心技能。"), angle("内容框架", "给出问题—取舍—结果的创始人发帖模板。")],
            score_factors={"velocity": 97, "relevance": 95, "content_opportunity": 87},
        ),
        make_trend(
            "3d-vertical-ai", "Vertical AI 从 Copilot 走向系统级产品", "垂直 AI 正在深入行业工作流，不再停留在通用助手层。",
            86, "持续高热", "hot", "+73%", "46.1K", "@ycombinator · @sama", 645,
            "三天内垂直 AI 融资与客户案例帖增长 73%，医疗、法律和销售场景贡献最高。",
            "GO DEEP, NOT BROAD", "3", "领跑的垂直行业",
            "Vertical AI 的机会，不是给每个行业套一个聊天框。\n\n真正的价值来自理解行业数据、审批路径与责任边界，并把模型嵌进完整工作流。\n\n越深入流程，越难被通用产品替代。",
            ["#VerticalAI", "#B2BSaaS", "#Workflow"],
            [angle("行业地图", "比较医疗、法律与销售三类垂直机会。"), angle("护城河", "解释流程深度为何比模型差异更持久。"), angle("反聊天框", "挑战简单套壳，强调系统级产品设计。")],
            score_factors={"velocity": 89, "relevance": 99, "content_opportunity": 92},
        ),
        make_trend(
            "3d-human-ai-teams", "Human + AI Team Design 成为管理议题", "企业开始讨论如何设计人机协作职责，而不只是采购更多 AI 工具。",
            79, "值得关注", "watch", "+42%", "27.8K", "@OpenAI · @paulg", 391,
            "职责分工类长帖在三天内获得 9.6K 次收藏，管理者受众占互动用户的 41%。",
            "DESIGN THE TEAM", "41%", "互动用户来自管理岗位",
            "部署 AI 工具，不等于拥有 AI 团队。\n\n真正需要被设计的是职责：AI 做哪些执行，人在哪些节点判断，失败由谁发现。\n\n未来的组织设计，会同时包含人和 Agent。",
            ["#FutureOfWork", "#Management", "#AIAgents"],
            [angle("组织设计", "讨论人和 Agent 的职责边界。"), angle("管理清单", "给管理者一套人机工作流检查问题。"), angle("失败机制", "从异常发现与责任归属切入。")],
            score_factors={"velocity": 80, "relevance": 88, "content_opportunity": 100},
        ),
    ],
    "7d": [
        make_trend(
            "7d-open-agent-stack", "Open Agent Stack 形成开发者生态", "一周趋势显示，Agent 基础设施正在从零散组件走向开放技术栈。",
            90, "周度领跑", "surging", "+104%", "126K", "@OpenAI · @karpathy", 1480,
            "过去七天 64 个开源 Agent 项目获得显著增长，工具调用和可观察性项目占新增 Star 的 57%。",
            "THE AGENT STACK OPENS", "64", "高速增长的开源项目",
            "Agent 生态正在重演云原生早期的路径：模型之上，工具、记忆、评测和可观察性快速分层。\n\n开放技术栈会加速试错，也会让真正的产品差异回到工作流和用户体验。",
            ["#OpenSource", "#AgentStack", "#DeveloperTools"],
            [angle("生态全景", "拆解 Agent Stack 的关键技术层。"), angle("开源数据", "用 64 个项目的增长展示开发者动量。"), angle("产品差异", "讨论基础设施标准化后，产品护城河在哪里。")],
            score_factors={"velocity": 98, "relevance": 90, "content_opportunity": 86},
        ),
        make_trend(
            "7d-small-model-economics", "Small Model Economics 改写 AI SaaS 毛利", "一周数据表明，模型路由与垂直小模型开始显著改善单位经济模型。",
            85, "周度高热", "hot", "+69%", "94K", "@sama · @ycombinator", 1106,
            "成本复盘帖连续七天保持高收藏率，采用模型路由的团队报告平均推理成本下降 61%。",
            "MARGIN IS A MODEL CHOICE", "−61%", "平均推理成本",
            "AI SaaS 的毛利，不只由定价决定。\n\n当团队开始按任务路由模型，用更小、更专注的模型处理高频请求，成本结构就会发生根本变化。\n\n模型选择，正在成为商业模式设计。",
            ["#SmallModels", "#SaaSEconomics", "#AIInfrastructure"],
            [angle("单位经济", "用 61% 成本下降拆解毛利改善空间。"), angle("技术策略", "介绍按任务难度进行模型路由。"), angle("创始人财务", "从 runway 与定价角度讨论模型选择。")],
            score_factors={"velocity": 88, "relevance": 99, "content_opportunity": 92},
        ),
        make_trend(
            "7d-trust-layer", "Trust Layer 成为 AI 产品必备层", "权限、审计、引用和人工确认成为企业 AI 落地的共同要求。",
            80, "稳定增长", "steady", "+47%", "71K", "@OpenAI · @paulg", 864,
            "一周内企业 AI 采购讨论中，68% 的高互动帖子同时提到审计记录与人工确认。",
            "TRUST IS A FEATURE", "68%", "讨论同时关注审计与确认",
            "企业不会因为 AI 更聪明就完全信任它。\n\n信任来自可解释的来源、清晰的权限、完整的审计，以及在关键动作前让人确认。\n\nTrust layer 不是合规附件，而是产品能力。",
            ["#AITrust", "#EnterpriseAI", "#HumanInTheLoop"],
            [angle("采购视角", "解释企业客户真正担心的四类风险。"), angle("产品架构", "拆解引用、权限、审计和确认四层。"), angle("信任转化", "说明 Trust Layer 如何缩短企业销售周期。")],
            score_factors={"velocity": 79, "relevance": 91, "content_opportunity": 100},
        ),
    ],
}

DRAFT_STATE = {
    f"{trend['id']}:{draft['id']}": {"status": "pending", "text": draft["text"]}
    for trends in TREND_SETS.values()
    for trend in trends
    for draft in trend["drafts"]
}

# Approved copy is kept separately so the demo can inspect exactly what a human approved.
APPROVED_DRAFTS = {}


def aggregate_trend_status(trend):
    statuses = [DRAFT_STATE[f"{trend['id']}:{draft['id']}"]["status"] for draft in trend["drafts"]]
    if "approved" in statuses:
        return "approved"
    if all(status == "rejected" for status in statuses):
        return "rejected"
    return "pending"


def trends_payload(window_key):
    trends = sorted(deepcopy(TREND_SETS[window_key]), key=lambda item: item["score"], reverse=True)
    pick_labels = {
        1: "⭐ #1 TelyClaw 核心推荐",
        2: "🔥 #2 高度契合品牌",
        3: "◆ #3 高价值内容机会",
    }
    for rank, trend in enumerate(trends, start=1):
        for draft in trend["drafts"]:
            record = DRAFT_STATE[f"{trend['id']}:{draft['id']}"]
            draft["status"] = record["status"]
            draft["text"] = record["text"]
        trend["status"] = aggregate_trend_status(trend)
        trend["rank"] = rank
        trend["is_top_pick"] = rank <= 3
        trend["top_pick_label"] = pick_labels.get(rank)
    return {
        "window": window_key,
        "window_label": WINDOW_LABELS[window_key],
        "total_source_posts": sum(trend["source_post_count"] for trend in trends),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "scoring_model": {
            "name": "TelyClaw 趋势机会得分 V1",
            "weights": OPPORTUNITY_WEIGHTS,
            "principle": "高热度不等于高机会；品牌契合度拥有最高权重。",
        },
        "trends": trends,
    }


def dashboard_payload():
    payload = {
        "workspace": deepcopy(WORKSPACE),
        "accounts": deepcopy(MOCK_ACCOUNTS),
        "sync_activity": deepcopy(SYNC_ACTIVITY),
        "north_star_metric": deepcopy(NORTH_STAR_METRIC),
        "supporting_metrics": deepcopy(SUPPORTING_METRICS),
    }
    payload.update(trends_payload("4h"))
    return payload


@app.get("/")
def index():
    return render_template("index.html")


@app.get("/api/dashboard")
def dashboard():
    return jsonify(dashboard_payload())


@app.post("/api/accounts")
def add_account():
    payload = request.get_json(silent=True) or {}
    handle = str(payload.get("handle", "")).strip().lstrip("@")
    if not re.fullmatch(r"[A-Za-z0-9_]{2,30}", handle):
        return jsonify({"ok": False, "error": "请输入有效的 X 账户名称"}), 400
    normalized_handle = f"@{handle}"
    if any(account["handle"].lower() == normalized_handle.lower() for account in MOCK_ACCOUNTS):
        return jsonify({"ok": False, "error": "该账户已在监控列表中"}), 409
    account = {
        "id": f"custom-{uuid4().hex[:10]}",
        "name": str(payload.get("name") or handle),
        "handle": normalized_handle,
        "followers": "0",
        "initials": handle[:2].upper(),
        "color": ACCOUNT_COLORS[len(MOCK_ACCOUNTS) % len(ACCOUNT_COLORS)],
        "status": "active",
        "niche_tags": ["#Custom", "#Monitoring"],
        "posts_24h": 0,
        "last_active": "等待首次同步",
    }
    MOCK_ACCOUNTS.insert(0, account)
    SYNC_ACTIVITY.insert(0, {
        "id": f"activity-{uuid4().hex[:10]}",
        "time": "刚刚",
        "lead": "已将",
        "account": normalized_handle,
        "message": "加入监控队列，等待首次同步",
        "icon": "user-round-plus",
        "tone": "success",
    })
    del SYNC_ACTIVITY[6:]
    return jsonify({"ok": True, "account": deepcopy(account), "accounts": deepcopy(MOCK_ACCOUNTS), "sync_activity": deepcopy(SYNC_ACTIVITY)}), 201


@app.delete("/api/accounts/<account_id>")
def remove_account(account_id):
    account = next((item for item in MOCK_ACCOUNTS if item["id"] == account_id), None)
    if account is None:
        return jsonify({"ok": False, "error": "未找到该监控账户"}), 404
    MOCK_ACCOUNTS.remove(account)
    SYNC_ACTIVITY.insert(0, {
        "id": f"activity-{uuid4().hex[:10]}",
        "time": "刚刚",
        "lead": "已将",
        "account": account["handle"],
        "message": "从监控队列安全移除",
        "icon": "user-round-minus",
        "tone": "neutral",
    })
    del SYNC_ACTIVITY[6:]
    return jsonify({"ok": True, "removed_id": account_id, "accounts": deepcopy(MOCK_ACCOUNTS), "sync_activity": deepcopy(SYNC_ACTIVITY)})


@app.get("/api/trends")
def trends():
    window_key = request.args.get("window", "4h")
    if window_key not in TREND_SETS:
        return jsonify({"ok": False, "error": "不支持的时间窗口", "supported_windows": WINDOW_LABELS}), 400
    payload = trends_payload(window_key)
    payload["ok"] = True
    return jsonify(payload)


@app.post("/api/drafts/<trend_id>/decision")
def decide_draft(trend_id):
    return decide_draft_version(trend_id, "A")


@app.put("/api/drafts/<trend_id>/<draft_id>")
def save_draft_version(trend_id, draft_id):
    draft_id = draft_id.upper()
    status_key = f"{trend_id}:{draft_id}"
    if status_key not in DRAFT_STATE:
        return jsonify({"ok": False, "error": "未找到该内容草稿"}), 404
    payload = request.get_json(silent=True) or {}
    text = str(payload.get("text", "")).strip()
    if not text:
        return jsonify({"ok": False, "error": "草稿正文不能为空"}), 400
    if len(text) > 5000:
        return jsonify({"ok": False, "error": "草稿正文过长"}), 400
    DRAFT_STATE[status_key]["text"] = text
    DRAFT_STATE[status_key]["updated_at"] = datetime.now(timezone.utc).isoformat()
    if status_key in APPROVED_DRAFTS:
        APPROVED_DRAFTS[status_key]["text"] = text
        APPROVED_DRAFTS[status_key]["edited_at"] = DRAFT_STATE[status_key]["updated_at"]
    return jsonify({"ok": True, "trend_id": trend_id, "draft_id": draft_id, "text": text})


@app.post("/api/drafts/<trend_id>/<draft_id>/decision")
def decide_draft_version(trend_id, draft_id):
    draft_id = draft_id.upper()
    status_key = f"{trend_id}:{draft_id}"
    if status_key not in DRAFT_STATE:
        return jsonify({"ok": False, "error": "未找到该内容草稿"}), 404
    payload = request.get_json(silent=True) or {}
    decision = payload.get("decision")
    if decision not in {"approved", "rejected"}:
        return jsonify({"ok": False, "error": "审核操作必须为批准或拒绝"}), 400
    text = str(payload.get("text", DRAFT_STATE[status_key]["text"])).strip()
    if not text:
        return jsonify({"ok": False, "error": "草稿正文不能为空"}), 400
    if len(text) > 5000:
        return jsonify({"ok": False, "error": "草稿正文过长"}), 400
    updated_at = datetime.now(timezone.utc).isoformat()
    DRAFT_STATE[status_key].update({"status": decision, "text": text, "updated_at": updated_at})
    if decision == "approved":
        APPROVED_DRAFTS[status_key] = {
            "trend_id": trend_id,
            "draft_id": draft_id,
            "text": text,
            "approved_at": updated_at,
        }
    else:
        APPROVED_DRAFTS.pop(status_key, None)
    trend = next(
        (item for trends in TREND_SETS.values() for item in trends if item["id"] == trend_id),
        None,
    )
    return jsonify({
        "ok": True,
        "trend_id": trend_id,
        "draft_id": draft_id,
        "status": decision,
        "text": text,
        "trend_status": aggregate_trend_status(trend),
        "updated_at": updated_at,
        "approved_drafts_count": len(APPROVED_DRAFTS),
    })


if __name__ == '__main__':
    app.run(port=5051, debug=True)
