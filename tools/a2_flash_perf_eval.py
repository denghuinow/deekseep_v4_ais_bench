#!/usr/bin/env python3
import argparse
import csv
import json
import math
import os
import re
import shutil
import subprocess
import sys
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, List, Optional


def find_repo_root() -> Path:
    candidates = [Path.cwd(), *Path(__file__).resolve().parents]
    for candidate in candidates:
        if (candidate / "huawei-baseline" / "aisbench_datatest").is_dir():
            return candidate
    return Path(__file__).resolve().parents[1]


REPO_ROOT = find_repo_root()
DEFAULT_IMAGE_TAR = REPO_ROOT / "huawei-baseline" / "ais_bench_benchmark_image.tar.gz"
DEFAULT_IMAGE = "ghcr.io/aisbench/aisbench_benchmark:v3.1-20260415-master_aarch64_py_310"
SOURCE_DATA_DIR = REPO_ROOT / "huawei-baseline" / "aisbench_datatest"
CONTAINER_DATA_DIR = "/workspace/aisbench_datatest"
MODEL_ABBR = "vllm-api-stream-chat"
DATASET_ABBR = "gsm8k"


@dataclass(frozen=True)
class CaseSpec:
    case_id: str
    excel_row: int
    product: str
    scene: str
    input_label: str
    input_len: int
    output_len: int
    prefix_cache_ratio: float
    excel_concurrency: float
    parallel_strategy: str
    profile: str
    ttft_ms: float
    tpot_ms: float
    e2e_s: float
    output_tps: float
    qps: float
    qpm: float

    @property
    def concurrency(self) -> int:
        # 低并发(<10)只向上取整不加缓冲；高并发(>=10)四舍五入取整后 +2 作为复测缓冲。
        if self.excel_concurrency < 10:
            return max(1, math.ceil(self.excel_concurrency))
        return max(1, int(self.excel_concurrency + 0.5) + 2)

    @property
    def is_prefix_case(self) -> bool:
        return self.prefix_cache_ratio > 0


CASES: Dict[str, CaseSpec] = {
    "single-8k-throughput": CaseSpec("single-8k-throughput", 20, "A2 单机混部", "高吞吐", "8K", 8192, 1024, 0, 22.4196, "DP1TP8", "flash-a2-single-standard", 23885.8, 44.5, 297.079, 330.9014, 0.3231, 19.386),
    "single-8k-latency": CaseSpec("single-8k-latency", 21, "A2 单机混部", "低时延", "8K", 8192, 1024, 0, 1.9942, "DP1TP8", "flash-a2-single-standard", 1448.9, 25.6, 111.01, 73.7949, 0.0721, 4.326),
    "single-32k-throughput": CaseSpec("single-32k-throughput", 22, "A2 单机混部", "高吞吐", "32K", 32768, 1024, 0, 7.7876, "DP1TP8", "flash-a2-single-standard", 8929.5, 49.1, 243.165, 134.7558, 0.1316, 7.896),
    "single-32k-latency": CaseSpec("single-32k-latency", 23, "A2 单机混部", "低时延", "32K", 32768, 1024, 0, 1, "DP1TP8", "flash-a2-single-standard", 4020.5, 24.9, 58.976, 34.7254, 0.0339, 2.034),
    "single-128k-throughput": CaseSpec("single-128k-throughput", 24, "A2 单机混部", "高吞吐", "128K", 131072, 1024, 0, 1.9315, "DP1TP8", "flash-a2-single-standard", 18594.8, 48.6, 141.407, 28.966, 0.0283, 1.698),
    "single-128k-throughput-prefix": CaseSpec("single-128k-throughput-prefix", 25, "A2 单机混部", "高吞吐", "128K", 131072, 1024, 0.9, 9.8302, "DP1TP8", "flash-a2-single-prefix-cache", 10171.9, 52.5, 259.734, 157.6997, 0.154, 9.24),
    "single-128k-latency": CaseSpec("single-128k-latency", 26, "A2 单机混部", "低时延", "128K", 131072, 1024, 0, 0.9999, "DP1TP8", "flash-a2-single-standard", 15876.4, 31, 190.226, 21.5323, 0.021, 1.26),
    "single-128k-latency-prefix": CaseSpec("single-128k-latency-prefix", 27, "A2 单机混部", "低时延", "128K", 131072, 1024, 0.9, 0.9998, "DP1TP8", "flash-a2-single-prefix-cache", 4430.3, 26.5, 126.192, 32.4583, 0.0317, 1.902),
    "single-1m-long-prefix": CaseSpec("single-1m-long-prefix", 28, "A2 单机混部", "超长序列", "1M", 1048576, 1024, 0.99, 0.9999, "DP1TP8", "flash-a2-single-long-context", 25906, 171.1, 401.99, 5.0946, 0.005, 0.3),
    "8pd-8k-throughput": CaseSpec("8pd-8k-throughput", 29, "A2 8机PD分离", "高吞吐", "8K", 8192, 1024, 0, 625.8173, "P:DP8TP1 / D:DP32TP1", "flash-a2-8pd-standard", 18298.1, 44.6, 286.11, 10021.3176, 9.7864, 587.184),
    "8pd-8k-latency": CaseSpec("8pd-8k-latency", 30, "A2 8机PD分离", "低时延", "8K", 8192, 1024, 0, 14.5, "P:DP8TP1 / D:DP32TP1", "flash-a2-8pd-standard", 5707.9, 29, 35.5, 419, 0.41, 24.6),
    "8pd-32k-throughput": CaseSpec("8pd-32k-throughput", 31, "A2 8机PD分离", "高吞吐", "32K", 32768, 1024, 0, 207.8674, "P:DP8TP1 / D:DP32TP1", "flash-a2-8pd-standard", 42562, 32.1, 348.335, 2822.1029, 2.756, 165.36),
    "8pd-32k-latency": CaseSpec("8pd-32k-latency", 32, "A2 8机PD分离", "低时延", "32K", 32768, 1024, 0, 15.3699, "P:DP8TP1 / D:DP32TP1", "flash-a2-8pd-standard", 15403.1, 29.7, 190.824, 343.436, 0.3354, 20.124),
    "8pd-128k-throughput": CaseSpec("8pd-128k-throughput", 33, "A2 8机PD分离", "高吞吐", "128K", 131072, 1024, 0, 222.133, "P:DP8TP1 / D:DP32TP1", "flash-a2-8pd-standard", 290044.4, 30.9, 1478.256, 707.2506, 0.6907, 41.442),
    "8pd-128k-throughput-prefix": CaseSpec("8pd-128k-throughput-prefix", 34, "A2 8机PD分离", "高吞吐", "128K", 131072, 1024, 0.9, 226.4973, "P:DP8TP1 / D:DP32TP1", "flash-a2-8pd-prefix-cache", 285285.5, 30.8, 421.3, 732.0153, 0.7149, 42.894),
    "8pd-128k-latency": CaseSpec("8pd-128k-latency", 35, "A2 8机PD分离", "低时延", "128K", 131072, 1024, 0, 41.1916, "P:DP8TP1 / D:DP32TP1", "flash-a2-8pd-standard", 63258.3, 31, 442.831, 443.9795, 0.4336, 26.016),
    "8pd-1m-long-prefix": CaseSpec("8pd-1m-long-prefix", 36, "A2 8机PD分离", "超长序列", "1M", 1048576, 1024, 0.99, 1, "P:DP4TP8 / D:DP4TP8", "flash-a2-8pd-long-context", 29811.5, 35.7, 66.4, 15.4, 0.015, 0.9),
}


PREFIX_DATASET_SCRIPT = r'''
import argparse
import json
from pathlib import Path
from transformers import AutoTokenizer


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model-path", required=True)
    parser.add_argument("--input-len", type=int, required=True)
    parser.add_argument("--data-num", type=int, required=True)
    parser.add_argument("--prefix-ratio", type=float, required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    tokenizer = AutoTokenizer.from_pretrained(args.model_path)
    shared_len = max(1, int(args.input_len * args.prefix_ratio))
    suffix_len = max(1, args.input_len - shared_len)
    base = (
        "DeepSeek V4 Flash performance prefix cache evaluation. "
        "Keep the shared context identical across requests. "
    )
    shared_ids = (tokenizer.encode(base, add_special_tokens=False) * ((shared_len // 16) + 16))[:shared_len]
    shared_text = tokenizer.decode(shared_ids, skip_special_tokens=True)

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as f:
        for idx in range(args.data_num):
            suffix = (
                f"\nRequest unique suffix {idx}. "
                "Solve a short arithmetic problem and continue reasoning. "
            )
            suffix_ids = (tokenizer.encode(suffix, add_special_tokens=False) * ((suffix_len // 16) + 16))[:suffix_len]
            text = shared_text + tokenizer.decode(suffix_ids, skip_special_tokens=True)
            f.write(json.dumps({"question": text, "answer": "none"}, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    main()
'''


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run AISBench DeepSeek V4 Flash A2 baseline retests in Docker.")
    parser.add_argument("--case", action="append", choices=sorted(CASES), help="Case ID to run. Can be specified multiple times.")
    parser.add_argument("--all", action="store_true", help="Run all single-node and 8PD cases.")
    parser.add_argument("--all-single", action="store_true", help="Run all A2 single-node co-located cases.")
    parser.add_argument("--all-8pd", action="store_true", help="Run all A2 8-machine PD cases.")
    parser.add_argument("--list-cases", action="store_true", help="Print case mapping table and exit.")
    parser.add_argument("--dry-run", action="store_true", help="Print Docker/AISBench commands without running them.")
    parser.add_argument("--host-ip", default="127.0.0.1", help="Inference service host/IP visible from the container.")
    parser.add_argument("--host-port", default="7000", help="Inference service port.")
    parser.add_argument("--model-name", default="ds", help="Served model name.")
    parser.add_argument("--model-path", default="/data/models/Eco-Tech/DeepSeek-V4-Flash-w8a8-mtp", help="Model/tokenizer path inside the container.")
    parser.add_argument("--model-mount", action="append", default=["/data/models:/data/models"], help="Docker volume for model files. Can be repeated.")
    parser.add_argument("--image", default=DEFAULT_IMAGE, help="AISBench Docker image tag.")
    parser.add_argument("--image-tar", default=str(DEFAULT_IMAGE_TAR), help="Local AISBench Docker image tar.gz path.")
    parser.add_argument("--summarizer", choices=["stable_stage", "default_perf"], default="stable_stage", help="AISBench performance summarizer.")
    parser.add_argument("--request-rate", default="0", help="AISBench request_rate.")
    parser.add_argument("--repeat", type=int, default=1, help="Repeat count passed to aisbench_test.py.")
    parser.add_argument("--data-num-multiplier", type=int, default=4, help="data_num = concurrency * multiplier unless --data-num is set.")
    parser.add_argument("--data-num", type=int, default=None, help="Override request count for every case.")
    parser.add_argument("--pressure", action="store_true", help="Run ais_bench in pressure mode by patching aisbench_test.py command.")
    parser.add_argument("--pressure-time", type=int, default=30, help="Pressure test duration in seconds when --pressure is enabled.")
    parser.add_argument("--output-dir", default=None, help="Host output directory.")
    parser.add_argument("--no-load-image", action="store_true", help="Skip docker image inspect/load.")
    parser.add_argument("--no-ipc-host", action="store_true", help="Do not run the benchmark container with --ipc=host.")
    parser.add_argument("--docker-shm-size", default="128g", help="Docker --shm-size used when --no-ipc-host is set.")
    return parser.parse_args()


def selected_cases(args: argparse.Namespace) -> List[CaseSpec]:
    ids: List[str] = []
    if args.all:
        ids.extend(CASES)
    if args.all_single:
        ids.extend(k for k, v in CASES.items() if v.product == "A2 单机混部")
    if args.all_8pd:
        ids.extend(k for k, v in CASES.items() if v.product == "A2 8机PD分离")
    if args.case:
        ids.extend(args.case)
    deduped = list(dict.fromkeys(ids))
    return [CASES[case_id] for case_id in deduped]


def print_cases(cases: Iterable[CaseSpec] = CASES.values()) -> None:
    headers = [
        "Case ID", "Excel 行", "产品组合", "场景", "输入", "输出",
        "Prefix Cache", "Excel 并发", "脚本并发", "并行策略", "Profile",
    ]
    rows = []
    for case in cases:
        rows.append([
            case.case_id, case.excel_row, case.product, case.scene,
            case.input_label, f"{case.output_len}", f"{case.prefix_cache_ratio:g}",
            f"{case.excel_concurrency:g}", case.concurrency, case.parallel_strategy, case.profile,
        ])
    widths = [max(len(str(row[i])) for row in [headers] + rows) for i in range(len(headers))]
    print(" | ".join(str(headers[i]).ljust(widths[i]) for i in range(len(headers))))
    print("-|-".join("-" * width for width in widths))
    for row in rows:
        print(" | ".join(str(row[i]).ljust(widths[i]) for i in range(len(row))))


def run_cmd(cmd: List[str], dry_run: bool = False, cwd: Optional[Path] = None) -> subprocess.CompletedProcess:
    print("+ " + " ".join(shell_quote(part) for part in cmd))
    if dry_run:
        return subprocess.CompletedProcess(cmd, 0)
    return subprocess.run(cmd, cwd=str(cwd) if cwd else None, check=True)


def shell_quote(value: str) -> str:
    if re.match(r"^[A-Za-z0-9_@%+=:,./-]+$", value):
        return value
    return "'" + value.replace("'", "'\"'\"'") + "'"


def ensure_image(args: argparse.Namespace) -> None:
    if args.no_load_image or args.dry_run:
        return
    inspect = subprocess.run(["docker", "image", "inspect", args.image], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if inspect.returncode == 0:
        return
    image_tar = Path(args.image_tar)
    if not image_tar.exists():
        raise FileNotFoundError(f"Docker image not found locally and image tar does not exist: {image_tar}")
    run_cmd(["docker", "load", "-i", str(image_tar)])


def prepare_case_dir(case: CaseSpec, root: Path, args: argparse.Namespace) -> Path:
    case_dir = root / f"{case.excel_row:02d}_{case.case_id}"
    if case_dir.exists():
        shutil.rmtree(case_dir)
    shutil.copytree(SOURCE_DATA_DIR, case_dir)
    (case_dir / "make_prefix_dataset.py").write_text(PREFIX_DATASET_SCRIPT, encoding="utf-8")
    config = f'''# Generated by tools/a2_flash_perf_eval.py for {case.case_id}
DATASET_PATH = "{CONTAINER_DATA_DIR}"
WORK_PATH = "/benchmark/"
MODEL_NAME = "{args.model_name}"
MODEL_PATH = "{args.model_path}"
HOST_IP = "{args.host_ip}"
HOST_PORT = "{args.host_port}"
DEFAULT_PERFORMANCE_TEST = "{args.summarizer}"
'''
    (case_dir / "config.py").write_text(config, encoding="utf-8")
    if args.pressure:
        patch_pressure_command(case_dir / "aisbench_test.py", args.pressure_time)
    return case_dir


def patch_pressure_command(path: Path, pressure_time: int) -> None:
    text = path.read_text(encoding="utf-8")
    old = "--mode perf --summarizer {DEFAULT_PERFORMANCE_TEST} --debug"
    new = f"--mode perf --summarizer {{DEFAULT_PERFORMANCE_TEST}} --pressure --pressure-time {pressure_time} --debug"
    path.write_text(text.replace(old, new), encoding="utf-8")


def case_data_num(case: CaseSpec, args: argparse.Namespace) -> int:
    if args.data_num is not None:
        return args.data_num
    return max(case.concurrency, case.concurrency * args.data_num_multiplier)


def build_container_inner_cmd(case: CaseSpec, args: argparse.Namespace) -> str:
    data_num = case_data_num(case, args)
    dataset_arg = ""
    prefix_cmd = ""
    if case.is_prefix_case:
        dataset_name = f"{case.case_id}_prefix.jsonl"
        dataset_path = f"{CONTAINER_DATA_DIR}/{dataset_name}"
        prefix_cmd = (
            "python3 make_prefix_dataset.py "
            f"--model-path {shell_quote(args.model_path)} "
            f"--input-len {case.input_len} "
            f"--data-num {data_num} "
            f"--prefix-ratio {case.prefix_cache_ratio} "
            f"--output {shell_quote(dataset_path)} && "
        )
        dataset_arg = f" --dataset {shell_quote(dataset_path)}"
    return (
        f"cd {CONTAINER_DATA_DIR} && "
        f"{prefix_cmd}"
        "python3 aisbench_test.py "
        f"--input_len {case.input_len} "
        f"--output_len {case.output_len} "
        f"--data_num {data_num} "
        f"--concurrency {case.concurrency} "
        f"--request_rate {shell_quote(str(args.request_rate))} "
        f"--repeat {args.repeat}"
        f"{dataset_arg}"
    )


def build_docker_cmd(case_dir: Path, case: CaseSpec, args: argparse.Namespace) -> List[str]:
    cmd = ["docker", "run", "--rm", "--net=host"]
    if args.no_ipc_host:
        cmd.extend(["--shm-size", args.docker_shm_size])
    else:
        cmd.append("--ipc=host")
    cmd.extend(["-v", f"{case_dir}:{CONTAINER_DATA_DIR}"])
    for mount in args.model_mount:
        cmd.extend(["-v", mount])
    inner = build_container_inner_cmd(case, args)
    cmd.extend([args.image, "bash", "-lc", inner])
    return cmd


def parse_number(value: object) -> Optional[float]:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    match = re.search(r"-?\d+(?:\.\d+)?", text)
    return float(match.group(0)) if match else None


def read_perf_csv(path: Path) -> Dict[str, float]:
    if not path.exists():
        return {}
    metrics: Dict[str, float] = {}
    with path.open("r", encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            name = row.get("Performance Parameters") or row.get("Performance Parameter")
            if not name:
                continue
            avg = parse_number(row.get("Average"))
            if avg is not None:
                metrics[f"{name}_average"] = avg
            n = parse_number(row.get("N"))
            if n is not None:
                metrics[f"{name}_n"] = n
    return metrics


def read_perf_json(path: Path) -> Dict[str, float]:
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    metrics: Dict[str, float] = {}
    for metric, by_stage in data.items():
        if not isinstance(by_stage, dict):
            continue
        for stage_value in by_stage.values():
            value = parse_number(stage_value)
            if value is not None:
                metrics[metric] = value
                break
    return metrics


def latest_perf_dir(case_dir: Path) -> Optional[Path]:
    perf_dirs = sorted(case_dir.glob(f"outputs/default/*/performances/{MODEL_ABBR}"))
    return perf_dirs[-1] if perf_dirs else None


def pct_diff(actual: Optional[float], baseline: float) -> Optional[float]:
    if actual is None or baseline == 0:
        return None
    return round((actual - baseline) / baseline * 100, 4)


def summarize_case(case: CaseSpec, case_dir: Path, exit_code: int, args: argparse.Namespace) -> Dict[str, object]:
    perf_dir = latest_perf_dir(case_dir)
    csv_metrics: Dict[str, float] = {}
    json_metrics: Dict[str, float] = {}
    if perf_dir:
        csv_metrics = read_perf_csv(perf_dir / f"{DATASET_ABBR}.csv")
        json_metrics = read_perf_json(perf_dir / f"{DATASET_ABBR}.json")

    actual_ttft = csv_metrics.get("TTFT_average")
    actual_tpot = csv_metrics.get("TPOT_average")
    actual_e2e_ms = csv_metrics.get("E2EL_average")
    actual_output_tps = json_metrics.get("Output Token Throughput") or csv_metrics.get("OutputTokenThroughput_average")
    actual_qps = json_metrics.get("Request Throughput")

    return {
        "case_id": case.case_id,
        "excel_row": case.excel_row,
        "product": case.product,
        "scene": case.scene,
        "input": case.input_label,
        "output": case.output_len,
        "prefix_cache_ratio": case.prefix_cache_ratio,
        "excel_concurrency": case.excel_concurrency,
        "script_concurrency": case.concurrency,
        "data_num": case_data_num(case, args),
        "parallel_strategy": case.parallel_strategy,
        "profile": case.profile,
        "exit_code": exit_code,
        "perf_dir": str(perf_dir) if perf_dir else "",
        "baseline_ttft_ms": case.ttft_ms,
        "actual_ttft_ms": actual_ttft,
        "ttft_diff_pct": pct_diff(actual_ttft, case.ttft_ms),
        "baseline_tpot_ms": case.tpot_ms,
        "actual_tpot_ms": actual_tpot,
        "tpot_diff_pct": pct_diff(actual_tpot, case.tpot_ms),
        "baseline_e2e_s": case.e2e_s,
        "actual_e2e_s": round(actual_e2e_ms / 1000, 6) if actual_e2e_ms is not None else None,
        "e2e_diff_pct": pct_diff((actual_e2e_ms / 1000) if actual_e2e_ms is not None else None, case.e2e_s),
        "baseline_output_tps": case.output_tps,
        "actual_output_tps": actual_output_tps,
        "output_tps_diff_pct": pct_diff(actual_output_tps, case.output_tps),
        "baseline_qps": case.qps,
        "actual_qps": actual_qps,
        "qps_diff_pct": pct_diff(actual_qps, case.qps),
        "baseline_qpm": case.qpm,
    }


def write_summary(rows: List[Dict[str, object]], output_dir: Path) -> None:
    json_path = output_dir / "summary.json"
    csv_path = output_dir / "summary.csv"
    json_path.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    if not rows:
        return
    with csv_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def write_case_manifest(case: CaseSpec, case_dir: Path, docker_cmd: List[str], args: argparse.Namespace) -> None:
    manifest = {
        "case": asdict(case),
        "script_concurrency": case.concurrency,
        "data_num": case_data_num(case, args),
        "docker_cmd": docker_cmd,
        "container_cmd": build_container_inner_cmd(case, args),
    }
    (case_dir / "case_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> int:
    args = parse_args()
    if args.list_cases:
        print_cases()
        return 0

    cases = selected_cases(args)
    if not cases:
        print("No case selected. Use --case, --all-single, --all-8pd, --all, or --list-cases.", file=sys.stderr)
        return 2

    output_dir = Path(args.output_dir) if args.output_dir else REPO_ROOT / "outputs" / "a2_flash_perf_eval" / datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir.mkdir(parents=True, exist_ok=True)
    ensure_image(args)

    rows: List[Dict[str, object]] = []
    for case in cases:
        print(f"\n=== Running {case.case_id} (Excel row {case.excel_row}) ===")
        case_dir = prepare_case_dir(case, output_dir, args)
        docker_cmd = build_docker_cmd(case_dir, case, args)
        write_case_manifest(case, case_dir, docker_cmd, args)
        exit_code = 0
        try:
            run_cmd(docker_cmd, dry_run=args.dry_run)
        except subprocess.CalledProcessError as exc:
            exit_code = exc.returncode
            print(f"Case {case.case_id} failed with exit code {exit_code}", file=sys.stderr)
        rows.append(summarize_case(case, case_dir, exit_code, args))
        write_summary(rows, output_dir)

    print(f"\nSummary written to: {output_dir / 'summary.csv'}")
    print(f"Summary JSON written to: {output_dir / 'summary.json'}")
    return 1 if any(row["exit_code"] for row in rows) else 0


if __name__ == "__main__":
    raise SystemExit(main())
