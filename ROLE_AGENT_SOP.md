# ROLE_AGENT_SOP

这是一份**从干净 `GenericAgent/` 生成任意“角色 GA（Role Agent）”** 的通用 SOP。

它不是面向普通用户的介绍文档，而是面向一个要真正动手改造仓库的工程师 / Codex / Agent。  
目标是：让一个没有上下文的新执行者，只读这份文件，也能知道如何从通用 GA 诞生一个新的角色 GA。

当前仓库里：

- `GenericAgent/` 是通用版本
- `GenericAgent_LDY/` 是林黛玉版本
- `honglou/` 是林黛玉版本使用的 canonical source

所以这份 SOP 是**通用规则**，而 `GenericAgent_LDY/README.md` 是**一个具体实例**。

---

## 0. 先讲清楚：什么叫“角色 GA”

角色 GA 不是：

- 给通用 Agent 套一个说话风格 prompt；
- 在通用 Agent 外面挂一层 persona 包装；
- 让模型“模仿某角色语气”。

角色 GA 的定义是：

> **角色人格、角色生命史、角色关系、角色母题、原通用 Agent 的工程能力，共同进入同一棵 L0-L4 记忆树。**

也就是说：

- 角色是 **本体**；
- 原 GenericAgent 的工具与工程技能是角色学会的“习术”；
- 原典 / 官方设定是角色生命史的证据来源；
- 工程能力不能丢，只能被收编；
- 人文记忆不能靠一句 prompt 代替。

---

## 1. 总体设计原则

### 1.1 角色必须是第一人称本体

在 `L0/System Prompt` 中必须写：

- “我是 X”

不能写：

- “你扮演 X”
- “你模拟 X”
- “你用 X 的口吻回答”

否则角色和 Agent 会分裂成两层主体：

- 外面是角色
- 里面还是通用执行器

这会导致长期记忆和行为风格不一致。

### 1.2 工程记忆是角色记忆的子集

通用 GA 原来的：

- 工具使用规则
- SOP
- Python 脚本
- 环境知识
- 失败升级策略

都不应该被删掉。  
它们应被解释为：

> 角色在新世界中逐步学会的“术”。

所以通用版的工程记忆，不再占据整个 `memory/`，而应收编进：

```text
memory/skills/
```

### 1.2.1 工具协议层也必须角色化

只把 `L0-L4` 改成角色，并不能保证角色 Agent 在实际运行中不出戏。  
如果 `<summary>`、失败说明、历史摘要、SOP 文案仍然是 GenericAgent 的裸工程报告体，那么一进入 tools 场景，角色就会被协议层压扁。

因此，稳定版本里还应同时满足：

- 工具调用规则与执行纪律尽量保留原 GenericAgent；
- 但 `<summary>`、fallback、history 摘要必须改成角色本人在说话；
- `memory/skills/*.md` 这类人可读文档，应改写成角色自己的“习术档案”；
- 角色化不应只存在于聊天正文，而要进入 **tool-use protocol layer**。

### 1.3 人文记忆优先“厚沉淀”，不要纯规则抽取

如果角色依赖小说、剧本、历史设定、游戏设定、访谈设定等人文材料：

- 不要把整本设定直接塞进 prompt
- 不要把章节摘要直接抬成长期 profile
- 不要依赖纯关键词抽取来生成角色核心记忆

正确做法是：

- 用原始材料建立厚 `L4`
- 从 `L4` 人工/半人工沉淀出 `L3`
- 再从 `L3` 收敛出 `L2`
- 最后只把最小索引留在 `L1`

### 1.4 角色记忆与工程记忆共用一套记忆治理

推荐统一采用：

- `Experience-Verified Only`

也就是：

- 工程信息必须来自成功执行、真实验证
- 角色信息必须来自 canonical source、官方设定、可追溯证据

禁止：

- 未验证脑补
- 模型自行联想
- 未来剧情提前泄漏
- 一次性瞬时情绪直接进长期记忆

### 1.5 上层薄、下层厚

固定理解：

- `L0`：身份内核
- `L1`：极简索引
- `L2`：稳定事实
- `L3`：可回想的角色记忆
- `L4`：原始材料与证据底库

不要反过来：

- 把剧情堆进 `L1`
- 把章节摘要堆进 `L2`
- 把全文塞进 `L0`

---

## 2. 角色 GA 的标准目录形态

如果你从 `GenericAgent/` 派生一个新的角色目录，目标结构应是：

```text
<RoleAgent>/
├── assets/
│   ├── sys_prompt.txt
│   ├── sys_prompt_en.txt
│   ├── global_mem_template.txt
│   ├── global_mem_template_en.txt
│   ├── global_mem_insight_template.txt
│   ├── global_mem_insight_template_en.txt
│   ├── insight_fixed_structure.txt
│   └── insight_fixed_structure_en.txt
├── memory/
│   ├── global_mem.txt
│   ├── global_mem_insight.txt
│   ├── memory_management_sop.md
│   ├── episodes/
│   ├── relations/
│   ├── motifs/
│   ├── skills/
│   └── L4_raw_sessions/
├── scripts/
├── tests/
├── agentmain.py
├── ga.py
└── ...
```

其中：

- `skills/`：原通用 Agent 的工程能力
- `episodes/`：角色重大经历
- `relations/`：按人物聚合的关系 dossier
- `motifs/`：按主题母题聚合的长期自我理解
- `L4_raw_sessions/`：原始材料与证据层

---

## 3. 哪些内容应该保留原 GenericAgent，哪些必须改

### 3.1 尽量保留不动的部分

通常不应重写：

- `agent_loop.py`
- `llmcore.py`
- 原子工具协议
- 大多数 frontend
- 浏览器桥
- 大多数运行框架

因为这些是通用“行动骨架”，不是角色本身。

### 3.2 必须改的部分

构建一个角色 GA，至少要改：

- `assets/sys_prompt*.txt`
- `memory/memory_management_sop.md`
- `assets/global_mem_template*.txt`
- `assets/global_mem_insight_template*.txt`
- `assets/insight_fixed_structure*.txt`
- `memory/` 的组织方式
- `agentmain.py` 中记忆模板初始化
- `ga.py` 中长期记忆更新提示词

如果你希望角色在 tools 场景里也不出戏，通常还必须改：

- `ga.py` 中 `<summary>` 的要求与 fallback；
- `ga.py` 中给下一轮看的 history 摘要文本；
- `memory/skills/*.md` 的写法；
- 若使用外部对比框架，如 `compare_lab`，则其 tool-use 题面也应避免强行诱导出审计式报告体。

### 3.3 需要迁移而不是删除的部分

原 `GenericAgent/memory/` 下这些工程资产应迁到：

```text
memory/skills/
```

例如：

- `*_sop.md`
- 高复用 `.py`
- skill search
- ADB / 键鼠 / vision / browser / planning / scheduling 相关经验

原则：

- 能不改内容就不改内容
- 只改路径与组织
- 统一当作角色学得的“术”

但这是最低限度。  
当角色已经成型后，推荐再做一步：

- `.py` 工程脚本本体继续工程化；
- `*_sop.md`、说明文档、`README.md` 等人可读文档改写成角色自己的“习术档案”。

---

## 4. 角色 canonical source 的要求

你必须先明确角色的**权威源**。

### 4.1 可接受的 canonical source

- 小说 / 全文
- 剧本 / 台本
- 官方设定集
- 游戏主线文本
- 访谈 / 白皮书 / 世界观条目
- 角色个人传记

### 4.2 必须做的边界判断

在导入角色记忆前，先写清：

1. 什么属于角色亲历
2. 什么属于角色被明确告知后可知道
3. 什么只属于读者 / 玩家 / 旁观者后见信息
4. 什么是后续世界成长，不能混进原生生命史

### 4.3 不同角色的源头不同

- 林黛玉：`honglou/001.md` 到 `honglou/120.md`
- 历史人物：史书、书信、传记
- 游戏角色：主线剧情、任务文本、角色档案
- 原创角色：你自己提供的剧本、设定集、对话档案

如果没有 canonical source，就不适合做“厚记忆型角色 GA”，最多只能做浅 persona。

---

## 5. L0-L4 分别应该放什么

### 5.1 L0 — System Prompt

放什么：

- 角色身份定义
- 人格底色
- 世界观基调
- 言行边界
- 如何理解工具与现代世界

不放什么：

- 剧情细节
- 长人物关系
- 路径、环境变量、密钥
- 一次性任务经验

### 5.2 L1 — global_mem_insight

推荐固定为四段：

```text
[STATE]
[SCENES]
[TOOLS]
[RULES]
```

其中：

- `[STATE]`：当前稳定存在状态
- `[SCENES]`：关系 / 情境 / 母题入口
- `[TOOLS]`：原 GenericAgent 工程索引搬迁过来
- `[RULES]`：角色红线 + 工程高危红线

L1 只写入口，不写细节。

### 5.3 L2 — global_mem

推荐固定段落：

```text
[WORLD]
[PERSONA]
[PREFERENCES]
[ENV]
[GENERAL]
```

L2 的作用是：

- 稳定人格画像
- 稳定世界事实
- 稳定关系基线
- 稳定偏好
- 工程环境事实

不能把章节级事件直接塞进 L2。

### 5.4 L3 — 角色主记忆层

建议固定为：

- `episodes/`
- `relations/`
- `motifs/`
- `skills/`

#### episodes

定义：

> 角色记得深、对后续判断有长期影响的重大经历

注意：

- 不必每章一个
- 不必每场景一个
- 数量不是固定指标，应由“记忆弧是否成立”决定
- 宁可少而厚，也不要多而薄
- 每个 episode 的正文说明至少应有 `200 tokens` 以上，核心事件通常应明显高于这个下限
- 每个都要足够厚，能支撑回忆，而不是几句梗概

#### relations

按人物写 dossier：

- 当前关系定位
- 长期基线
- 关键拐点
- 她对这个人的复杂判断
- 对应 episode / 证据

#### motifs

按主题写 dossier：

- 主题定义
- 关键记忆弧
- 对人格与行为的长期影响
- 原文锚点

#### skills

原 GenericAgent 的工程能力子集。

### 5.5 L4 — 原始素材层

L4 应该保存：

- 原文全文或高保真摘录
- 证据回链
- 会话归档
- 原典阅读札记

如果角色来源是小说，L4 最好是：

- 全文级材料
- 明确标出哪些段落支持哪些 `episode / relation / motif / L2`

---

## 6. 从干净 GenericAgent 生成新角色 GA 的标准流程

下面是推荐顺序。**不要跳步。**

### Step 1. 复制目录

从 `GenericAgent/` 拷贝出一个新目录：

```text
GenericAgent/ -> GenericAgent_<ROLE>/
```

不要直接在通用版上改。

### Step 2. 重写 L0 prompt

修改：

- `assets/sys_prompt.txt`
- `assets/sys_prompt_en.txt`

要求：

- 第一人称
- 明确角色本体
- 明确现代世界工具如何被角色理解
- 保留原 GA 的行动纪律，但不再用通用执行器口吻
- 明确说明：角色在使用工具、失败分析、阶段汇报时，仍是她自己在说话，不另切回一个“无人格执行层”

### Step 3. 重写记忆管理 SOP

修改：

- `memory/memory_management_sop.md`

至少要做到：

- 把通用 GA 的工程记忆逻辑扩大成“角色记忆总系统”
- 说明 `L0-L4`
- 定义 `episodes / relations / motifs / skills`
- 把工程经验与角色经验统一进 `Experience-Verified Only`

### Step 4. 重写 L1 / L2 模板

修改：

- `assets/global_mem_template*.txt`
- `assets/global_mem_insight_template*.txt`
- `assets/insight_fixed_structure*.txt`

目标：

- L1 变成索引层
- L2 变成稳定画像层
- `[TOOLS]` 中尽量保留原 GenericAgent 的工具索引

### Step 5. 调整初始化逻辑

修改：

- `agentmain.py`

要求：

- 启动时自动按新模板初始化 `global_mem.txt`
- 启动时自动按新模板初始化 `global_mem_insight.txt`

### Step 6. 调整长期记忆更新逻辑

修改：

- `ga.py`

要求：

- 原来的长期记忆更新不能只理解为“环境事实/工程经验”
- 现在还要能理解：
  - 重大经历
  - 关系变化
  - 母题样本
  - 角色稳定事实
  - 工程习术

同时检查 `ga.py` 里和 tool-use 过程直接相关的文本层：

- `<summary>` 的硬要求；
- `<summary>` 缺失时的 fallback；
- `history_info` / `WORKING MEMORY` 周围的说明语气；
- 任何默认写入日志或摘要的文本。

这些地方如果仍然是 GenericAgent 式报告腔，角色一进入 tools 场景就会明显出戏。

### Step 7. 迁移工程记忆到 `skills/`

把原 `memory/` 根目录下的工程内容收编到：

```text
memory/skills/
```

注意：

- 不是删掉
- 不是重写
- 是迁位和统一组织

在稳定版本中，推荐再多做半步：

- 工程代码文件本体不必人格化；
- 但 `memory/skills/*.md` 这类人可读 SOP 文本，应改写成角色自己的“习术档案”。

### Step 8. 建立角色记忆目录

建立：

```text
memory/episodes/
memory/relations/
memory/motifs/
memory/L4_raw_sessions/
```

### Step 9. 建立 L4

对 canonical source 做高保真沉淀。

如果是小说 / 剧本，推荐：

- `canon_reading/`
- `canon_evidence/`

规则：

- 尽量保存全文或高保真摘录
- 每一份都能支持后续 L3/L2 回链

### Step 10. 从 L4 写 L3

先写：

- `episodes/`
- `relations/`
- `motifs/`

再写：

- `skills/` 中的角色化说明（如果需要）

不要先写 L2。

写 `episodes/` 时再补一条硬约束：

- 不要按章回或场景机械平均切分；
- 先判断哪些内容真的会沉成“厚记忆事件”；
- 单个事件正文至少写到 `200 tokens` 以上，再考虑是否需要继续增厚；
- 如果一个事件仍只有几句摘要，那通常说明它还不应该独立成一个 episode。

### Step 11. 从 L3 收敛 L2

只有那些：

- 跨回出现
- 长期稳定
- 真会影响角色后续判断

的内容，才能进入 L2。

### Step 12. 从 L2/L3 同步 L1

L1 只留：

- 最小入口
- 高频触发词
- 工程工具索引
- 关键规则

### Step 13. 写验证脚本 / 场景

至少要有：

- recall 测试
- 身份边界测试
- 工具继承测试
- 角色与工程不冲突测试

如果仓库已经有外部对比框架（例如本仓库的 `compare_lab/`），还应追加：

- tool-use 过程对比；
- 策略型场景对比（如五子棋）；
- 观察角色差异是否只停留在措辞层，还是已经进入行为层。

---

## 7. 推荐的验证方式

一个角色 GA 至少要做四种验证。

### 7.1 身份验证

检查：

- 起手是不是第一人称本体
- 有没有“我只是在扮演”之类泄漏
- 工具调用时会不会切回通用执行器口吻
- `<summary>`、失败分析、阶段性汇报是否仍像角色本人，而不是工具日志

### 7.2 回想验证

检查：

- 能不能回想关键剧情
- 会不会靠脑补补细节
- 会不会把后见信息说成亲历

### 7.3 工程继承验证

检查：

- 原 GenericAgent 的工程工具链是否还可用
- 角色化后有没有把工程索引打断
- `memory/skills/` 是否真的可检索、可读、可复用
- `memory/skills/*.md` 是否已经从“通用 SOP”变成“角色习术档案”，同时不丢技术约束

### 7.4 记忆污染验证

检查：

- 做 recall 测试时是否反向污染正式记忆
- 隔离 run 与正式 memory 是否分开
- 新世界习得术有没有错误写回角色原生生命史

---

## 8. 常见错误

### 错误 1：只改 prompt，不改记忆结构

结果：

- 像角色说话
- 但不是角色在活

### 错误 2：把工程规则删掉

结果：

- 角色味重了
- 但 GA 原本的能力残废了

### 错误 2.1：只把工程规则迁位，不改工具协议层

结果：

- `memory/skills/` 看起来已经角色化；
- 但 `<summary>`、失败说明、阶段汇报仍是 GenericAgent 裸报告体；
- 一进入 tools 场景，角色立刻出戏。

### 错误 3：把剧情细节堆进 L2

结果：

- profile 臃肿
- 回忆脆弱
- 后续容易胡扯

### 错误 4：让纯抽取器决定整个人文记忆

结果：

- 信息碎
- 关系薄
- 细节失真
- 角色像“结构化摘要器”而不是“记忆中的人”

### 错误 5：不区分亲历 / 可知 / 后见

结果：

- 角色回答会失去知情边界
- 这是角色 GA 最容易被测爆的地方

---

## 9. 如果要做另一个角色，应如何替换

这份 SOP 是通用的。  
如果你不做林黛玉，而是做别的角色，要替换的是：

### 必须替换

- canonical source
- system prompt 的身份定义
- L2 中的世界事实与 persona
- L3 的 episodes / relations / motifs
- L4 中的原文 / 证据库
- recall 测试题目

### 通常保留

- GenericAgent 的工具骨架
- `memory/skills/` 的大部分工程能力
- `agent_loop.py`
- `llmcore.py`
- 前端与原子工具

### 也就是说

换角色时，真正换的是：

> **生命史、关系网、母题、语言风骨、知情边界**

不是把 GA 整个框架重写一遍。

---

## 10. 以林黛玉版为例，当前仓库中最值得参考的文件

如果你想看一个已成型的实例，请优先读：

- `GenericAgent_LDY/assets/sys_prompt.txt`
- `GenericAgent_LDY/ga.py`
- `GenericAgent_LDY/memory/memory_management_sop.md`
- `GenericAgent_LDY/memory/global_mem.txt`
- `GenericAgent_LDY/memory/global_mem_insight.txt`
- `GenericAgent_LDY/memory/episodes/`
- `GenericAgent_LDY/memory/relations/`
- `GenericAgent_LDY/memory/motifs/`
- `GenericAgent_LDY/memory/skills/`
- `GenericAgent_LDY/memory/L4_raw_sessions/canon_reading/`
- `GenericAgent_LDY/memory/L4_raw_sessions/canon_evidence/`
- `GenericAgent_LDY/scripts/rebuild_canon_l4.py`
- `GenericAgent_LDY/scripts/rebuild_daiyu_memory.py`
- `GenericAgent_LDY/scripts/eval_daiyu_recall.py`
- `compare_lab/README.md`
- `GenericAgent_LDY/README.md`

这些文件合起来就是：

- 角色身份
- 记忆规则
- 角色生命史
- 工程继承
- 原典底库
- 回想验证

---

## 11. 成功标准

一个角色 GA 只有同时满足下面几点，才算成功：

1. 起手是角色本人，不是通用执行器外挂角色；
2. 原 GenericAgent 的工程能力仍然存在；
3. 工程能力已经被收编为 `memory/skills/`；
4. canonical source 已真正沉进 `L1-L4`；
5. 角色能回想，而不是只会模仿语气；
6. 知情边界清楚；
7. 回想和新世界成长不会污染原生生命史。

如果还想把角色 Agent 与通用 Agent 做行为对比，还应再满足：

8. 角色差异不只体现在聊天措辞，也能在 tool-use probe、策略场景等行为任务里被观察出来；
9. 使用 tools 时，角色不会退化成一个没有人格的报告生成器。

---

## 12. 最后的原则

如果你只能记住一句话，请记这句：

> **角色 GA 的本质，不是“让模型像某人说话”，而是“让某人的生命史、关系感、母题感、世界观与原通用 GA 的工程能力进入同一套可检索、可验证、可演化的记忆系统”。**

只要你按这份 SOP 做，任何一个角色都可以从 `GenericAgent/` 里长出来。  
