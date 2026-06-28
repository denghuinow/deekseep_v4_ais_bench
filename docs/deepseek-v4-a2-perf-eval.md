# DeepSeek V4 Flash A2 性能复测说明

本文档说明如何使用 `tools/a2_flash_perf_eval.py` 复测 Huawei 基线 Excel 中的 DeepSeek V4 Flash A2 性能指标，并生成对比报告。

## 适用范围

脚本覆盖发布版 Excel `huawei-baseline/(0623修正)DeepSeek V4测试数据出口-对外发布版本.xlsx` 中 `V4 Flash模型性能基线` 的 A2 场景：

- `A2 单机混部`：Excel 第 20-28 行
- `A2 8机PD分离`：Excel 第 29-36 行

脚本只做客户端复测和报告生成，不部署、不启动、不停止推理服务。

## 环境要求

运行机器需要满足：

- 已安装 Docker
- 当前机器能访问被测 OpenAI 兼容推理服务
- 项目内存在 AISBench 镜像包：
  `huawei-baseline/ais_bench_benchmark_image.tar.gz`
- 模型 tokenizer 路径能挂载进容器，默认使用：
  `/data/models:/data/models`

## 数据集来源

脚本会把项目内的 AISBench 数据目录复制到每个 case 的临时工作目录：

```text
huawei-baseline/aisbench_datatest/
```

普通非 Prefix Cache case 会使用其中的：

```text
huawei-baseline/aisbench_datatest/GSM8K.jsonl
```

执行时，`aisbench_test.py` 调用 `process_dataset.py`，基于 `GSM8K.jsonl` 和 `--model-path` 指定的 tokenizer 生成目标输入长度的数据集，例如：

```text
GSM8K-in8192-bs8.jsonl
GSM8K-in131072-bs8.jsonl
```

Prefix Cache case 不直接使用 `GSM8K.jsonl` 作为请求数据，而是在临时工作目录生成共享前缀 JSONL，用于模拟 Excel 中的 Prefix Cache 命中率目标。

脚本默认使用镜像：

```text
ghcr.io/aisbench/aisbench_benchmark:v3.1-20260415-master_aarch64_py_310
```

如果本地 Docker 没有该镜像，脚本会自动执行：

```bash
docker load -i huawei-baseline/ais_bench_benchmark_image.tar.gz
```

## 查看 Case 对照表

先查看 case 与 Excel 行号的对应关系：

```bash
python3 tools/a2_flash_perf_eval.py --list-cases
```

也可以查看 skill 内的静态对照表：

```text
skills/deepseek-v4-a2-perf/references/cases.md
```

## 推荐执行流程

### 1. 先 dry-run

dry-run 只打印 Docker 和 AISBench 命令，不会请求推理服务：

```bash
python3 tools/a2_flash_perf_eval.py \
  --dry-run \
  --case single-8k-latency \
  --host-ip 10.30.31.131 \
  --host-port 7000 \
  --model-name ds \
  --model-path /data/models/Eco-Tech/DeepSeek-V4-Flash-w8a8-mtp
```

确认以下内容正确：

- `--host-ip` / `--host-port`
- `--model-name`
- `--model-path`
- Docker 挂载路径
- case 对应的输入长度、输出长度、并发数

### 2. 跑一个低风险 case

建议先跑低时延小规格 case：

```bash
python3 tools/a2_flash_perf_eval.py \
  --case single-8k-latency \
  --host-ip 10.30.31.131 \
  --host-port 7000 \
  --model-name ds \
  --model-path /data/models/Eco-Tech/DeepSeek-V4-Flash-w8a8-mtp
```

### 3. 按需跑单机混部或 8PD

执行所有单机混部 case：

```bash
python3 tools/a2_flash_perf_eval.py \
  --all-single \
  --host-ip 10.30.31.131 \
  --host-port 7000 \
  --model-name ds \
  --model-path /data/models/Eco-Tech/DeepSeek-V4-Flash-w8a8-mtp
```

执行所有 8机 PD case：

```bash
python3 tools/a2_flash_perf_eval.py \
  --all-8pd \
  --host-ip 10.30.31.131 \
  --host-port 7000 \
  --model-name deepseek_v4 \
  --model-path /data/models/Eco-Tech/DeepSeek-V4-Flash-w8a8-mtp
```

执行指定多个 case：

```bash
python3 tools/a2_flash_perf_eval.py \
  --case single-8k-throughput \
  --case 8pd-8k-throughput \
  --host-ip 10.30.31.131 \
  --host-port 7000 \
  --model-name ds \
  --model-path /data/models/Eco-Tech/DeepSeek-V4-Flash-w8a8-mtp
```

## 输出文件

默认输出目录：

```text
outputs/a2_flash_perf_eval/<timestamp>/
```

关键文件：

| 文件 | 说明 |
|---|---|
| `summary.csv` | 汇总报告，适合打开表格查看 |
| `summary.json` | 结构化汇总报告 |
| `<row>_<case>/case_manifest.json` | 单个 case 的参数和 Docker 命令 |
| `<row>_<case>/outputs/default/<time>/performances/vllm-api-stream-chat/gsm8k.csv` | AISBench 单请求性能指标 |
| `<row>_<case>/outputs/default/<time>/performances/vllm-api-stream-chat/gsm8k.json` | AISBench 全局性能指标 |

可以用 `--output-dir` 指定输出目录：

```bash
python3 tools/a2_flash_perf_eval.py \
  --case single-8k-latency \
  --output-dir outputs/manual_single_8k_latency \
  --host-ip 10.30.31.131 \
  --host-port 7000 \
  --model-name ds \
  --model-path /data/models/Eco-Tech/DeepSeek-V4-Flash-w8a8-mtp
```

## 报告字段

`summary.csv` / `summary.json` 主要字段：

| 字段 | 说明 |
|---|---|
| `case_id` | 脚本 case 名 |
| `excel_row` | 对应发布版 Excel 行号 |
| `product` | `A2 单机混部` 或 `A2 8机PD分离` |
| `prefix_cache_ratio` | Excel 中的 Prefix Cache 命中率目标 |
| `excel_concurrency` | Excel 原始系统并发，对应 AISBench 结果中的 Concurrency（实际并发） |
| `script_concurrency` | 传给 AISBench 的 `--concurrency`，对应结果中的 Max Concurrency（最大并发上限）；低并发(<10)向上取整、高并发(>=10)四舍五入取整后 +2 |
| `baseline_*` | Excel 基线值 |
| `actual_*` | 本次 AISBench 实测值 |
| `*_diff_pct` | 实测值相对基线的百分比差异 |
| `perf_dir` | AISBench 原始结果目录 |

脚本只展示差异，不做 Pass/Fail 判定。

## Prefix Cache 场景

这些 case 会生成共享前缀数据集：

- `single-128k-throughput-prefix`
- `single-128k-latency-prefix`
- `single-1m-long-prefix`
- `8pd-128k-throughput-prefix`
- `8pd-1m-long-prefix`

客户端脚本只能构造共享前缀请求，不能直接验证服务端 Prefix Cache 实际命中率。报告中的 `prefix_cache_ratio` 是 Excel 目标值和数据集构造目标。

## 常用参数

| 参数 | 默认值 | 说明 |
|---|---|---|
| `--summarizer` | `stable_stage` | AISBench 汇总口径 |
| `--request-rate` | `0` | 小于 0.1 时并发一次性发送 |
| `--repeat` | `1` | 传给 `aisbench_test.py` 的重复次数 |
| `--data-num-multiplier` | `4` | 默认请求数为脚本并发数的 4 倍 |
| `--data-num` | 无 | 强制覆盖所有 case 的请求数 |
| `--pressure` | 关闭 | 给 AISBench 增加压测模式 |
| `--pressure-time` | `30` | 压测时长，单位秒 |
| `--no-load-image` | 关闭 | 跳过镜像检查和 `docker load` |
| `--no-ipc-host` | 关闭 | 不使用 Docker `--ipc=host` |
| `--docker-shm-size` | `128g` | `--no-ipc-host` 时配置容器 `/dev/shm` |

### 并发数与请求数取数规则

先区分两个 AISBench 结果指标，避免混淆：

- **Concurrency**：实际并发数，即测试期间同时在途的请求数。Excel 基线表中的「系统并发数」指的就是这个值。
- **Max Concurrency**：最大并发数，即测试期间允许同时在途的请求数上限，对应我们运行脚本时通过 `--concurrency` 指定的值。

我们无法直接指定「实际并发」，只能指定「最大并发」。因此脚本并发数（`--concurrency`）在 Excel 系统并发数基础上取整并加缓冲，让实测 Concurrency 有空间达到基线水平，避免上限过低压不出基线压力：

- 低并发（<10）：向上取整，不加缓冲；
- 高并发（>=10）：四舍五入取整后 +2；
- 总请求数 = 脚本并发数 × 4（可用 `--data-num-multiplier` 调整，或 `--data-num` 强制覆盖）。

例如 `single-8k-throughput` Excel 系统并发 22.42 → 脚本最大并发 24、总请求数 96，实测 Concurrency 应落在 22 附近；`single-8k-latency` Excel 系统并发 1.99 → 脚本最大并发 2、总请求数 8。`--list-cases` 输出的「Excel 并发 / 脚本并发」两列即为该规则结果，其中「脚本并发」即 Max Concurrency 上限。

默认 Docker 命令会带 `--ipc=host`，用于避免高并发 AISBench 在 Docker 默认 64MB `/dev/shm` 下触发 `Bus Error`。如果运行环境禁止 host IPC，可改用：

```bash
python3 tools/a2_flash_perf_eval.py \
  --case 8pd-8k-throughput \
  --no-ipc-host \
  --docker-shm-size 128g \
  --host-ip 10.30.31.131 \
  --host-port 7000 \
  --model-name deepseek_v4 \
  --model-path /data/models/Eco-Tech/DeepSeek-V4-Flash-w8a8-mtp
```

## 注意事项

- 8PD 高吞吐 case 并发很高，例如 `8pd-8k-throughput` 的脚本并发为 628，执行前确认服务端和客户端资源足够。
- 如果执行 `8pd-8k-throughput` 等高并发 case 出现 `Bus Error`，优先确认 Docker 命令是否包含 `--ipc=host`；不使用 host IPC 时请增大 `--docker-shm-size`。
- 128K / 1M case 耗时长、数据集大，建议先 dry-run 并确认输出目录磁盘空间。
- 如果模型路径不是 `/data/models/...`，需要同时调整 `--model-path` 和 `--model-mount`。
- 如果服务端 `served-model-name` 是 `deepseek_v4` 而不是 `ds`，必须设置 `--model-name deepseek_v4`。
- 当前脚本复用 `huawei-baseline/aisbench_datatest/aisbench_test.py`，每个 case 都复制一份临时工作目录运行，不会改原始数据目录。
