# NDX vNext 可视化流程总图

写作日期：2026-07-05

这份文件只做一件事：把 NDX vNext 画成一张**可阅读、可批注、可讨论改动影响**的大图。

如果你要缩放、拖动和贴批注，优先打开同目录的 `NDX_流程总图.canvas`。

读法很简单：

- **主链路**：实线箭头，表示一次正式研究从数据到报告的流动。
- **说明卡**：虚线箭头连出来的白话说明，讲这个节点的职能、工作方式、特点、禁区和改动影响。
- **红线节点**：不能破坏的架构规则。
- **旁路节点**：新闻、浏览器、sidecar、legacy 等辅助材料，默认不是主证据。

## 一张大图

```mermaid
flowchart TD
    %% ========= 主链路 =========
    A["A. Data Collect<br/>采集正式数据"] --> B["B. Data Audit<br/>检查数据质量、时间边界、缺口"]
    B --> C["C. Context Build<br/>构建上下文，并按 L1-L5 隔离"]
    C --> D["D. ObjectCanon<br/>先定义投资对象"]

    D --> E1["E1. L1 Analyst<br/>宏观、利率、流动性条件"]
    D --> E2["E2. L2 Analyst<br/>信用、波动、风险偏好"]
    D --> E3["E3. L3 Analyst<br/>广度、集中度、内部健康"]
    D --> E4["E4. L4 Analyst<br/>估值、盈利、风险溢价"]
    D --> E5["E5. L5 Analyst<br/>价格趋势、技术执行"]

    E1 --> F["F. Bridge<br/>跨层冲突、共振、传导"]
    E2 --> F
    E3 --> F
    E4 --> F
    E5 --> F

    F --> G["G. SynthesisPacket<br/>压缩证据索引，保留关键矛盾"]
    G --> H["H. Thesis Builder<br/>形成主论点初稿"]
    H --> I["I. Critic<br/>攻击弱逻辑、越权推理"]
    H --> J["J. Risk Sentinel<br/>写清风险边界和触发器"]
    I --> K["K. Reviser<br/>修订论点，但不抹平冲突"]
    J --> K
    K --> L["L. Final Adjudicator<br/>最终裁决和发布判断"]
    L --> M["M. Native Brief / Workbench<br/>给人看的报告和探索台"]
    L --> N["N. Prompt Inspector / Run Review / DataIntegrity<br/>审计与发布闸门"]

    %% ========= 辅助旁路 =========
    O["O. News / Event / Browser / Sidecar<br/>候选材料、背景线索"] -.-> F
    O -.-> M
    P["P. Legacy HTML / legacy adapter<br/>兼容导出，不是主分析"] -.-> M

    %% ========= 红线 =========
    R1["红线 1<br/>约束：L1-L5 运行时上下文隔离<br/>各层不能偷看其他层本轮数据、摘要、结论"] -.-> C
    R1 -.-> E1
    R1 -.-> E2
    R1 -.-> E3
    R1 -.-> E4
    R1 -.-> E5

    R2["红线 2<br/>约束：新闻、浏览器、sidecar 默认不是 L1-L5 evidence_ref<br/>只能当候选线索，除非升级为正式数据源"] -.-> O
    R2 -.-> F

    R3["红线 3<br/>约束：blocked / unpublishable 不能发布<br/>DataIntegrity 和 publish status 是硬闸门"] -.-> N
    R3 -.-> L

    R4["红线 4<br/>约束：冲突是资产<br/>反证、张力、未解决问题必须保留"] -.-> F
    R4 -.-> K
    R4 -.-> L

    %% ========= 说明卡：数据段 =========
    A_note["说明卡 A<br/><b>职能</b>：采正式数据、人工输入、回测日期、来源元信息。<br/><b>怎么工作</b>：把不同工具函数和数据源整理成数据包或不可变快照。<br/><b>特点</b>：像资料员，不是研究员。<br/><b>禁区</b>：不能提前下市场结论，不能把失败数据包装成有效证据。<br/><b>改动影响</b>：会影响整条链的证据地基。"] -.-> A

    B_note["说明卡 B<br/><b>职能</b>：检查数据是否能进入分析。<br/><b>怎么工作</b>：DataIntegrity 检查空数据、坏数据、未来数据、发布状态。<br/><b>特点</b>：是发布闸门，不是建议项。<br/><b>禁区</b>：不能因为模型能写报告就放过 blocked / unpublishable。<br/><b>改动影响</b>：影响系统能不能安全发布。"] -.-> B

    C_note["说明卡 C<br/><b>职能</b>：把大数据包变成全局上下文和五个分层上下文。<br/><b>怎么工作</b>：Bridge 可读全局 brief；L1-L5 只能读自己的 layer_context_brief。<br/><b>特点</b>：它是导航，不是证据本身。<br/><b>禁区</b>：不能把全局跨层候选关系塞给 L1-L5。<br/><b>改动影响</b>：最容易影响上下文隔离。"] -.-> C

    D_note["说明卡 D<br/><b>职能</b>：先说清楚我们到底判断什么对象。<br/><b>怎么工作</b>：默认 NDX 是主对象，QQQ 是可交易代理，NDXE / QEW 是等权参考。<br/><b>特点</b>：它定义所有指标的解释边界。<br/><b>禁区</b>：不能把 QQQ 写成全部科技股，不能忽视集中度。<br/><b>改动影响</b>：会影响 L1-L5、Bridge、Final 的口径。"] -.-> D

    %% ========= 说明卡：五层分析 =========
    E1_note["说明卡 E1<br/><b>职能</b>：判断宏观贴现环境。<br/><b>输入</b>：只吃 L1 数据 + ObjectCanon + L1 指标法典。<br/><b>怎么工作</b>：看名义利率、真实利率、通胀补偿、政策利率、流动性。<br/><b>特点</b>：回答长期分母压力，不直接给买卖点。<br/><b>禁区</b>：不能看 L4 估值或 L5 趋势来改写 L1 结论。<br/><b>改动影响</b>：影响利率 vs 估值、宏观压力等 Bridge 冲突。"] -.-> E1

    E2_note["说明卡 E2<br/><b>职能</b>：判断市场风险偏好。<br/><b>输入</b>：只吃 L2 数据 + ObjectCanon + L2 指标法典。<br/><b>怎么工作</b>：看信用利差、VIX/VXN、波动期限结构、流动性压力。<br/><b>特点</b>：像风险体温计。<br/><b>禁区</b>：不能把 VIX 低写成安全，不能把 VIX 高写成必买。<br/><b>改动影响</b>：影响信用、波动、风险偏好的传导路径。"] -.-> E2

    E3_note["说明卡 E3<br/><b>职能</b>：判断 NDX 内部是不是健康。<br/><b>输入</b>：只吃 L3 数据 + ObjectCanon + L3 指标法典。<br/><b>怎么工作</b>：看广度、等权相对市值加权、Top10 权重、新高新低、成分股均线占比。<br/><b>特点</b>：拆穿“指数涨 = 全部健康”的错觉。<br/><b>禁区</b>：不能用 L5 价格趋势替代内部健康。<br/><b>改动影响</b>：影响狭窄牛市、集中度风险、置信度。"] -.-> E3

    E4_note["说明卡 E4<br/><b>职能</b>：判断估值、盈利和风险溢价。<br/><b>输入</b>：只吃 L4 数据 + ObjectCanon + L4 指标法典。<br/><b>怎么工作</b>：优先用 Wind NDX 指数级估值；其他来源按发言权降级。<br/><b>特点</b>：最需要数据来源等级和口径说明。<br/><b>禁区</b>：不能用技术指标证明估值便宜，不能拿当前网页冒充历史回测数据。<br/><b>改动影响</b>：影响中长期赔率、估值主锚、Final 置信度。"] -.-> E4

    E5_note["说明卡 E5<br/><b>职能</b>：判断趋势和执行节奏。<br/><b>输入</b>：只吃 L5 数据 + ObjectCanon + L5 指标法典。<br/><b>怎么工作</b>：看价格趋势、均线、动量、波动和技术位置。<br/><b>特点</b>：服务战术执行，不负责解释全部世界。<br/><b>禁区</b>：不能因为 RSI 超卖就说估值便宜，不能用价格强覆盖 L3 问题。<br/><b>改动影响</b>：影响战术动作、价格是否反映风险。"] -.-> E5

    %% ========= 说明卡：综合治理段 =========
    F_note["说明卡 F<br/><b>职能</b>：把五层分析连接起来。<br/><b>怎么工作</b>：输出 typed_conflicts、resonance_chains、transmission_paths、principal_contradiction。<br/><b>特点</b>：不是重新分析单指标，而是建模层与层之间的关系。<br/><b>禁区</b>：不能把冲突写没，不能把新闻当正式数值证据。<br/><b>改动影响</b>：影响主矛盾、跨层证据链、Thesis 质量。"] -.-> F

    G_note["说明卡 G<br/><b>职能</b>：把 Layer 和 Bridge 压缩成治理阶段可读的证据包。<br/><b>怎么工作</b>：整理 evidence_index、高严重度冲突、Objective Firewall、must-preserve risks。<br/><b>特点</b>：压缩信息，但不能压掉矛盾。<br/><b>禁区</b>：不能让 Thesis 绕过 Bridge 脑补关系。<br/><b>改动影响</b>：影响 Thesis / Critic / Risk / Final 看到什么。"] -.-> G

    H_note["说明卡 H<br/><b>职能</b>：写出主论点初稿。<br/><b>怎么工作</b>：只基于 SynthesisPacket 组织主要矛盾、价格反映、核心动作、战术动作。<br/><b>特点</b>：它是初稿，不是最终裁判。<br/><b>禁区</b>：不能跳过 Bridge 主要矛盾，不能脑补证据。<br/><b>改动影响</b>：影响报告主线和后续审查目标。"] -.-> H

    I_note["说明卡 I<br/><b>职能</b>：专门找 Thesis 的漏洞。<br/><b>怎么工作</b>：检查指标越权、证据不足、冲突被抹平、数据频率错配。<br/><b>特点</b>：像反方律师，不负责润色。<br/><b>禁区</b>：不能只写泛泛提醒，必须指出具体问题。<br/><b>改动影响</b>：影响系统自我纠错能力。"] -.-> I

    J_note["说明卡 J<br/><b>职能</b>：写清风险边界和可观察触发器。<br/><b>怎么工作</b>：把什么会推翻判断、哪些指标要观察、哪些风险必须保留写出来。<br/><b>特点</b>：重点是“系统什么时候会错”。<br/><b>禁区</b>：不能编造历史胜率、概率、点位阈值、回测收益。<br/><b>改动影响</b>：影响 Final 的边界感和读者行动风险。"] -.-> J

    K_note["说明卡 K<br/><b>职能</b>：吸收批评和风险，修订主论点。<br/><b>怎么工作</b>：削弱过度结论，补上触发器，保留未解决问题。<br/><b>特点</b>：不是把文字写顺，而是让结论更诚实。<br/><b>禁区</b>：不能为了顺滑抹平冲突。<br/><b>改动影响</b>：影响最终论点是否保留真实张力。"] -.-> K

    L_note["说明卡 L<br/><b>职能</b>：最终裁决。<br/><b>怎么工作</b>：检查 Layer、Bridge、Revised Thesis、Critic、Risk、Schema Guard、DataIntegrity。<br/><b>特点</b>：可以降低置信度，也可以拒绝发布。<br/><b>禁区</b>：不能跳过 blocked / unpublishable，不能编造点位和概率。<br/><b>改动影响</b>：影响最终立场、置信度、发布状态。"] -.-> L

    M_note["说明卡 M<br/><b>职能</b>：把研究产物展示给人。<br/><b>怎么工作</b>：brief 负责连续阅读，workbench 负责看盘探索，legacy 只兼容导出。<br/><b>特点</b>：展示层要帮助追证据、看冲突、看风险边界。<br/><b>禁区</b>：不能用漂亮页面掩盖证据问题，不能让 legacy 变回主分析。<br/><b>改动影响</b>：影响你能不能读懂和追问。"] -.-> M

    N_note["说明卡 N<br/><b>职能</b>：审计本轮到底发生了什么。<br/><b>怎么工作</b>：Prompt Inspector 看 prompt 和隔离；Run Review 看 data / bridge / thesis / risk / final；DataIntegrity 看发布状态。<br/><b>特点</b>：是复盘眼睛，不是事后洗白工具。<br/><b>禁区</b>：不能把失败复盘改写成成功结论。<br/><b>改动影响</b>：影响你能不能知道我到底改了什么、验证了什么。"] -.-> N

    %% ========= 样式 =========
    classDef main fill:#eef6ff,stroke:#2563eb,stroke-width:1.5px,color:#111827;
    classDef layer fill:#f0fdf4,stroke:#16a34a,stroke-width:1.5px,color:#111827;
    classDef gov fill:#fff7ed,stroke:#ea580c,stroke-width:1.5px,color:#111827;
    classDef output fill:#f5f3ff,stroke:#7c3aed,stroke-width:1.5px,color:#111827;
    classDef note fill:#ffffff,stroke:#94a3b8,stroke-dasharray:4 3,color:#111827;
    classDef redline fill:#fff1f2,stroke:#e11d48,stroke-width:2px,color:#111827;
    classDef side fill:#f8fafc,stroke:#64748b,stroke-dasharray:5 3,color:#111827;

    class A,B,C,D main;
    class E1,E2,E3,E4,E5 layer;
    class F,G,H,I,J,K,L gov;
    class M,N output;
    class A_note,B_note,C_note,D_note,E1_note,E2_note,E3_note,E4_note,E5_note,F_note,G_note,H_note,I_note,J_note,K_note,L_note,M_note,N_note note;
    class R1,R2,R3,R4 redline;
    class O,P side;
```

## 怎么用这张图批注改动

以后如果你让我“加一个模块”或“改一个 agent”，批注应该直接画在链路上，而不是写成一堆文件名。

### 批注模板：新增正式数据源

```mermaid
flowchart LR
    A["Data Collect<br/>新增数据源"] --> B["Data Audit<br/>日期、覆盖率、缺口检查"]
    B --> C["Context Build<br/>只送到对应层"]
    C --> D["对应 Lx Analyst<br/>更新本层分析"]
    D --> E["Bridge<br/>观察跨层影响"]
    E --> F["Final / Brief<br/>影响最终判断和展示"]

    X["批注<br/>必须说明来源、日期、覆盖率、回测可见性、缺失时如何降级"] -.-> A

    classDef changed fill:#ecfeff,stroke:#0891b2,stroke-width:2px,color:#111827;
    classDef warn fill:#fff1f2,stroke:#e11d48,stroke-width:2px,color:#111827;
    class A,B,C,D,E,F changed;
    class X warn;
```

### 批注模板：修改某个 agent

```mermaid
flowchart LR
    A["被修改 Agent<br/>例如 L4 Analyst"] --> B["直接输出<br/>LayerCard"]
    B --> C["Bridge<br/>跨层冲突/共振可能变化"]
    C --> D["SynthesisPacket"]
    D --> E["Thesis / Critic / Risk / Reviser"]
    E --> F["Final"]
    F --> G["Brief / Workbench"]

    R["红线检查<br/>不能让该 agent 看到其他层运行时数据"] -.-> A
    V["验证检查<br/>Prompt Inspector + Run Review + 相关测试"] -.-> F

    classDef changed fill:#ecfeff,stroke:#0891b2,stroke-width:2px,color:#111827;
    classDef warn fill:#fff1f2,stroke:#e11d48,stroke-width:2px,color:#111827;
    class A,B,C,D,E,F,G changed;
    class R,V warn;
```

### 批注模板：新增新闻/事件模块

```mermaid
flowchart LR
    A["News / Event Brief<br/>新闻和事件事实"] --> B["Integrated Synthesis Report<br/>综合总报告"]
    C["Pure Data vNext Report<br/>纯数据研报"] --> B

    A -.-> D["L1-L5 / Bridge / Thesis / Final<br/>纯数据主链<br/>禁止回流"]
    X["批注<br/>新闻可以解释背景，但不能冒充指标证据"] -.-> A

    classDef side fill:#f8fafc,stroke:#64748b,stroke-dasharray:5 3,color:#111827;
    classDef warn fill:#fff1f2,stroke:#e11d48,stroke-width:2px,color:#111827;
    class A,B,C side;
    class D,X warn;
```

## 每次改动必须附的图上批注

以后交付代码改动时，应该按这个格式贴在这份图下面：

```md
## 修改批注：YYYY-MM-DD 标题

改动节点：
- 例如：L3 Analyst、Bridge、Run Review

影响路径：
Data Collect -> Data Audit -> Context Build -> L3 Analyst -> Bridge -> SynthesisPacket -> Thesis -> Final -> Brief

我改了什么：
- 用人话说清楚，不只报文件名。

为什么要改：
- 解决哪个误判、缺口、阅读问题或审计问题。

不应该影响：
- 哪些层不该收到新数据。
- 哪些旁路材料不该升级成主证据。

我怎么验证：
- 跑了哪些检查。
- 结果是什么。
- 没跑什么，为什么没跑。

剩余风险：
- 还有什么不能保证。
- 下一轮真实 run 要重点看什么。
```

## 这版和上一版的区别

上一版的问题是：它把你的“可视化猜想”写成了长文档。

这一版改成：

- 图是主体。
- 每个节点都有挂在图上的说明卡。
- 红线直接画在图里。
- 新增模块和修改 agent 的批注方式也画成图。
- 文字只服务于读图，不再单独铺开解释。
