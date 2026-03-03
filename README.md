# pr_excavation 结果说明

本目录包含一次从 PSI‑BLAST 扩展序列开始，到聚类、二次多序列比对、RuvC 结构域拆分，再到 HHM profile 构建的完整结果。

## 流程配置与自动化

本项目已集成 **EvoMaster** 智能 Agent 框架（v0.1.0），作为构建科研智能体的基础设施。

## 实现内容（全部基于 EvoMaster）

本项目在原有流水线（`run_pipeline.py`）基础上，引入 EvoMaster 的 Agent + Tools + Session 机制，实现了一个**多 Agent 协作**的自动化实验框架，包含三类能力：

1. **实验管理 + 扫参（Sweep）**
   - Planner 生成多组参数组合（例如 `filter.min_length`、`cluster.min_seq_id`、`cluster.coverage`）。
   - Runner 为每组参数创建独立 trial 目录并执行一次完整 pipeline。
   - Reviewer 读取产物并给出打分与统计，写入汇总报告。

2. **异常诊断与自动调整（Diagnose & Auto-fix）**
   - 当某个 trial 运行失败（非 0 退出码），Diagnoser 会根据日志与常见问题做参数修复（例如把非法阈值拉回合理范围、降低线程/迭代以提升稳定性），然后触发重跑。

3. **参数自优化（Optimize）**
   - 基于 Sweep 的“当前最优 trial”，在其附近做邻域搜索（小幅度调整 `min_seq_id/coverage` 等），迭代尝试更优参数。

对应实现代码位于：
- `evomaster_integration/`：EvoMaster 多 Agent 集成代码
  - `multiagent_demo.py`：多 Agent 入口（sweep/diagnose/optimize + 报告输出）
  - `tools.py`：自定义工具（创建 trial、写 config、运行 pipeline、评估、诊断修复）
  - `simple_agents.py`：最小 Agent 封装（继承 EvoMaster BaseAgent）
  - `deterministic_llm.py`：演示用的确定性 LLM（不依赖外部 API Key，也能走通“Agent 调用 Tools”的流程）

## 如何调用 EvoMaster 来跑（多 Agent）

在项目目录下运行：

```bash
cd /data/wyw/pr_excavation
conda run -n bio_env python -m evomaster_integration.multiagent_demo
```

运行后会在当前目录生成：
- `evomaster_runs/run_YYYYMMDD_HHMMSS/`：一次运行的根目录
- `evomaster_runs/run_.../trials/<trial_id>/`：每个 trial 的独立工作目录（包含该 trial 的 config、日志、输出产物）
- `evomaster_runs/run_.../report.txt`：人类可读摘要
- `evomaster_runs/run_.../summary.json`：结构化汇总（便于程序分析/二次可视化）

### 1. 配置文件 `config.yaml`
您可以直接修改此文件中的数值，无需更改任何 Python 代码：
- `filter.min_length`: 最小序列长度（默认 150）。
- `cluster.min_seq_id`: 聚类相似度（默认 0.7，即 70%）。
- `mafft.threads`: 使用的 CPU 核心数。
- `split.min_domain_len`: 结构域拆分的最小长度。

### 2. 自动化运行脚本 `run_pipeline.py`
现在您可以通过一个命令运行整个流程：
```bash
python run_pipeline.py
```
该脚本会自动读取 `config.yaml` 中的参数并按顺序执行所有步骤。

## 流程概览（每一步做了什么）

1. **PSI‑BLAST 扩展序列**
   - 作用：从数据库中迭代找出更多与种子序列相似的蛋白序列。
   - 输出：`cas12p_1_psiblast.fas`

2. **长度过滤（删除 <150 aa）**
   - 作用：去掉过短的序列，减少噪音，避免影响比对质量。
   - 脚本：`filter_length.py`
   - 输出：`filtered.fasta`

3. **MAFFT 初步比对（快速模式）**
   - 作用：先做一版“粗略比对”，用于后续聚类/抽代表序列。
   - 输出：`alignment1.aln`

4. **MMSeqs2 聚类（70% identity / 70% coverage）**
   - 作用：把高度相似的序列合并成簇，只保留代表序列，减少冗余。
   - 输出：`cluster.tsv`（聚类关系表），`representative.fasta`（代表序列）

5. **代表序列二次比对（MAFFT 高精度模式，等价 E‑INS‑i）**
   - 作用：对代表序列做更精确的多序列比对。
   - 输出：`alignment2.aln`

6. **RuvC 结构域拆分（自动化脚本）**
   - 作用：把比对按保守区间自动切成 RuvC‑I / RuvC‑II / RuvC‑III 三段。
   - 脚本：`split_domains.py`
   - 输出：`RuvC-I.aln`、`RuvC-II.aln`、`RuvC-III.aln`

7. **构建 HHM profile（hhmake）**
   - 作用：把每个结构域的多序列比对转成 profile（HMM‑HMM 的输入）。
   - 输出：`RuvC-I.hhm`、`RuvC-II.hhm`、`RuvC-III.hhm`

## 文件清单与作用

- `cas12p_1_psiblast.fas`：PSI‑BLAST 扩展得到的原始序列集合。
- `filter_length.py`：长度过滤脚本（删除 <150 aa）。
- `filtered.fasta`：长度过滤后的序列集合。
- `alignment1.aln`：初步（快速）多序列比对结果。
- `cluster.tsv`：MMSeqs2 聚类结果表（每条序列所属簇）。
- `cluster_out_all_seqs.fasta`：MMSeqs2 输出的“聚类用全序列集合”，与输入序列一致，仅作为中间结果保留。
- `representative.fasta`：聚类后每个簇的代表序列。
- `alignment2.aln`：代表序列的高精度多序列比对结果。
- `split_domains.py`：结构域自动拆分脚本。
- `RuvC-I.aln` / `RuvC-II.aln` / `RuvC-III.aln`：三段结构域比对。
- `RuvC-I.hhm` / `RuvC-II.hhm` / `RuvC-III.hhm`：三段结构域的 HHM profile。
- `config.yaml`：流水线参数配置文件（把可调参数集中在一个地方）。
- `run_pipeline.py`：单次流水线入口脚本（读取 `config.yaml` 并依次执行各步骤）。
- `requirements.txt`：Python 依赖快照（包含 `evomaster`）。
- `evomaster_integration/`：EvoMaster 多 Agent 集成实现（见上面的“实现内容”）。
- `evomaster_runs/`：EvoMaster 运行产物目录（每次运行会自动生成；已在 `.gitignore` 中忽略，不会上传到 GitHub）。
- `.gitignore`：忽略超大文件与运行产物（例如 `alignment1.aln`、`evomaster_runs/`、`__pycache__/`）。

## 文件格式解释（非生信版）

### 1) FASTA / .fas / .fasta
- **用途**：存放序列。
- **结构**：
  - 每条序列以 `>` 开头的描述行
  - 下一行（或多行）是氨基酸序列
- **示例**：
  ```
  >seq_1
  MKKLLPTAA...GHT
  ```

### 2) ALN / .aln（多序列比对）
- **用途**：同一批序列被“对齐”到相同长度，用 `-` 表示插入缺口。
- **结构**：类似 FASTA，但每条序列有大量 `-`。
- **意义**：可以看到哪些位置在不同序列里是“同源”的。

### 3) TSV / .tsv（制表符分隔表）
- **用途**：表格数据（每列用 Tab 分隔）。
- **在本项目中**：`cluster.tsv` 的每一行通常表示“代表序列 与 成员序列”的对应关系。
- **示例**：
  ```
  rep_seq_1    member_seq_1
  rep_seq_1    member_seq_2
  ```

### 4) HHM / .hhm（HHsuite profile）
- **用途**：由多序列比对生成的 profile（HMM 表示），用于远缘同源搜索。
- **特点**：包含位置特异的概率矩阵，是“比对结果的统计模型”。
- **使用场景**：后续可用 `hhalign` 或 `hhsearch` 与其它 profile 比较。

## 如何快速复现（命令摘要）

```bash
# 1) 过滤长度
python /data/wyw/pr_excavation/filter_length.py \
  /data/wyw/pr_excavation/cas12p_1_psiblast.fas \
  /data/wyw/pr_excavation/filtered.fasta 150

# 2) 初步比对
conda run -n bio_env mafft --retree 1 --maxiterate 0 --thread 8 \
  /data/wyw/pr_excavation/filtered.fasta \
  > /data/wyw/pr_excavation/alignment1.aln

# 3) 聚类
conda run -n bio_env mmseqs easy-cluster \
  /data/wyw/pr_excavation/filtered.fasta \
  /data/wyw/pr_excavation/cluster_out \
  /data/wyw/pr_excavation/tmp \
  --min-seq-id 0.7 -c 0.7 --cov-mode 0
mv /data/wyw/pr_excavation/cluster_out_cluster.tsv /data/wyw/pr_excavation/cluster.tsv
mv /data/wyw/pr_excavation/cluster_out_rep_seq.fasta /data/wyw/pr_excavation/representative.fasta

# 4) 代表序列高精度比对
conda run -n bio_env mafft --genafpair --maxiterate 1000 --ep 0 --thread 128 \
  /data/wyw/pr_excavation/representative.fasta \
  > /data/wyw/pr_excavation/alignment2.aln

# 5) 结构域拆分
conda run -n bio_env python /data/wyw/pr_excavation/split_domains.py \
  /data/wyw/pr_excavation/alignment2.aln \
  /data/wyw/pr_excavation

# 6) HHM profile
conda run -n bio_env hhmake -i /data/wyw/pr_excavation/RuvC-I.aln -o /data/wyw/pr_excavation/RuvC-I.hhm
conda run -n bio_env hhmake -i /data/wyw/pr_excavation/RuvC-II.aln -o /data/wyw/pr_excavation/RuvC-II.hhm
conda run -n bio_env hhmake -i /data/wyw/pr_excavation/RuvC-III.aln -o /data/wyw/pr_excavation/RuvC-III.hhm
```

