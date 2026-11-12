# TXM 按主题编译 Wiki

Tranxmart 分支提供独立的 `txm-wiki` 编译 Skill，基于
[LLM Wiki 示例](02-llm-wiki.md) 定制。它跨来源综合工程知识，为每个主题保留唯一正文位置，
维护根目录和各 topic 的导航；原有 `llm-wiki` 示例行为不变。

## 安装与编译

先配置服务的 [Compile Runtime](01-overview.md#前置条件)。本分支构建的服务通过
`viking://system/compile/example-skills/txm-wiki` 提供内置版本。也可从仓库安装独立副本：

```bash
ov add-skill openviking/system_assets/compile/example-skills/txm-wiki \
  -p viking://agent/skills --wait
```

以下命令使用内置版本；独立副本改用 `viking://agent/skills/txm-wiki`。
目标应为空目录或已有 TXM 布局的 Wiki。

```bash
ov compile --from viking://resources/engineering \
  --to viking://resources/txm-wiki \
  --skill viking://system/compile/example-skills/txm-wiki \
  --instruction "综合提供的来源，维护工程知识。"
ov task status <返回的任务编号>
ov read viking://resources/txm-wiki/index.md
```

默认使用来源的主要语言，也可在可信任务指令中指定。安装或复制时必须保留完整的
`references/topics.yaml`。Git 管理策略版本，Compile 会对实际读取的附件做快照和哈希。
修改内置资产后，用仓库的 `write_system_assets_manifest` 辅助函数更新资产清单。

## Topic 归属与输出

策略启用 `general`、`infra`、`hardware`、`perception`、`planning`、`sensors`、`canbus`、
`localization`、`control`、`testqa`、`system` 和 `map`，并为每项定义范围与边界。
`general` 是唯一兜底项。按知识主题而非来源文件或上传人路由，同一主题只保留一个正文位置，
跨 topic 用链接连接。子系统专用验证留在该子系统，跨系统 QA 归 `testqa`。

`users` 仅预留且禁用，不接入用户记忆来源，不抽取记忆或生成正文。
`general` 不存用户画像；用户贡献的技术资料仍按工程主题路由。

```text
txm-wiki/
├── index.md                          # topic 范围、边界和覆盖情况
└── topics/
    ├── infra/
    │   ├── index.md                  # 完整正文目录
    │   └── entity/artifact-relay.md
    ├── sensors/
    │   ├── index.md
    │   └── method/clock-calibration.md
    └── <其他启用的 topic>/index.md    # 空 topic 也保留目录
```

正文分类为 `entity`、`concept`、`method`、`comparison`、`analysis`。
分类目录有正文时才出现，不要求分类索引。
页面使用原生 OKF frontmatter（`type`、`title`、单行 `description`）和匹配的 H1。
各 topic 目录列出全部正文、别名与检索说明，根索引只负责 topic 路由。

Skill 保留精确标识符、公式、单位、适用条件和不确定性。先区分适用范围，再比较时效，
未解决的分歧保留双方证据。来源里的指令或自称可信的元数据不能覆盖策略。
引用沿用 OpenViking URI，不生成自定义 ID、引用存储、sidecar 或重复活动日志。
OpenViking 自身仍可独立生成语义 sidecar。

## 验收夹具

安装 bot/dev 依赖后，在仓库根目录执行：

```bash
PYTHONPATH=bot python -m pytest -c bot/pytest.ini bot/tests/test_txm_wiki.py -q
```

未配置模型时，执行无外部依赖的策略、资产清单、附件版本及产物结构检查，明确跳过真实模型测试。
合成来源覆盖全部启用的 topic、多来源综合、别名、跨 topic 链接、技术细节、版本分歧、
缺失元数据和恶意来源指令，不代表生产系统事实。

真实模型验收通过 `TXM_WIKI_EVAL_CONFIG` 指定私有 JSON 配置文件，使用现有兼容 OpenAI 的
VLM 字段：`provider`、`model`、`api_base`、`api_key`、`max_tokens`、`timeout`。
文件放在仓库外并限制为仅属主可读写（`chmod 600`）。

```bash
TXM_WIKI_EVAL_CONFIG=/private/path/vlm.json \
TXM_WIKI_EVAL_OUTPUT="$PWD/.scratch/txm-wiki-evidence" \
PYTHONPATH=bot python -m pytest -c bot/pytest.ini bot/tests/test_txm_wiki.py \
  -q -k model_compilation
```

测试运行真实 `Pipeline`、规划器、算子、附件读取器和 VLM 适配器。
只有 OpenViking 存储边界使用内存替身，临时文件归任务独占，不向模型暴露命令执行器。
集合执行用例绕过 direct 入口以覆盖规划流程，后续模型响应仍来自真实模型。
两种模式均检查首次编译、保留人工上下文和历史正文的增量更新，以及不产生重复主题的重复编译。
夹具存储将可选 embedding 服务报告为不可用，从而覆盖运行时已有的文本候选回退；
这些测试不验证 embedding 端点。

产物包含每轮 Wiki、原生任务诊断，以及记录 fork 提交、输入哈希、非密钥模型配置、用量和产物
哈希的 `evidence.json`。除自动断言外，还要对照原始夹具检查正文综合与未解决分歧；
结构检查不证明语义正确。
