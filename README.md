# pr_excavation 结果说明

本目录包含一次从 PSI‑BLAST 扩展序列开始，到聚类、二次多序列比对、RuvC 结构域拆分，再到 HHM profile 构建的完整结果。

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


