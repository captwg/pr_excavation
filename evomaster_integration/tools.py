import json
import os
import shutil
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, ClassVar

import yaml

from evomaster.agent.tools.base import BaseTool, BaseToolParams


def _count_fasta_records(path: Path) -> int:
    n = 0
    with path.open("r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            if line.startswith(">"):
                n += 1
    return n


def _read_text(path: Path, max_bytes: int = 200_000) -> str:
    if not path.exists():
        return ""
    data = path.read_bytes()
    if len(data) > max_bytes:
        data = data[:max_bytes]
    try:
        return data.decode("utf-8", errors="replace")
    except Exception:
        return ""


def _set_nested(d: dict, dotted_key: str, value: Any) -> None:
    parts = dotted_key.split(".")
    cur = d
    for p in parts[:-1]:
        if p not in cur or not isinstance(cur[p], dict):
            cur[p] = {}
        cur = cur[p]
    cur[parts[-1]] = value


def _get_nested(d: dict, dotted_key: str, default=None):
    parts = dotted_key.split(".")
    cur = d
    for p in parts:
        if not isinstance(cur, dict) or p not in cur:
            return default
        cur = cur[p]
    return cur


class CreateTrialParams(BaseToolParams):
    name: ClassVar[str] = "create_trial"
    run_dir: str
    trial_id: str
    sample_n: int = 50
    source_fasta: str = "cas12p_1_psiblast.fas"


class CreateTrialTool(BaseTool):
    name: ClassVar[str] = "create_trial"
    params_class: ClassVar[type[BaseToolParams]] = CreateTrialParams

    def execute(self, session, args_json: str):
        params = self.parse_params(args_json)
        run_dir = Path(params.run_dir).absolute()
        trial_dir = run_dir / "trials" / params.trial_id
        trial_dir.mkdir(parents=True, exist_ok=True)
        (trial_dir / "logs").mkdir(exist_ok=True)

        project_root = Path.cwd().absolute()
        for fname in ["filter_length.py", "split_domains.py", "run_pipeline.py", "config.yaml"]:
            src = project_root / fname
            if src.exists():
                shutil.copy2(src, trial_dir / fname)

        src_fasta_path = (project_root / params.source_fasta).resolve()
        sampled_path = trial_dir / params.source_fasta
        self._sample_fasta(src_fasta_path, sampled_path, params.sample_n)

        obs = json.dumps(
            {
                "trial_dir": str(trial_dir),
                "sampled_fasta": str(sampled_path),
                "sample_n": params.sample_n,
            },
            ensure_ascii=False,
        )
        return obs, {"trial_dir": str(trial_dir)}

    def _sample_fasta(self, src: Path, dst: Path, n: int):
        if not src.exists():
            raise FileNotFoundError(str(src))
        out = []
        current = []
        kept = 0
        with src.open("r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                if line.startswith(">"):
                    if current:
                        out.extend(current)
                        kept += 1
                        if kept >= n:
                            break
                    current = [line]
                else:
                    if current:
                        current.append(line)
            if kept < n and current and kept < n:
                out.extend(current)
        dst.write_text("".join(out), encoding="utf-8")


class UpdateConfigParams(BaseToolParams):
    name: ClassVar[str] = "update_config"
    trial_dir: str
    overrides: dict[str, Any]


class UpdateConfigTool(BaseTool):
    name: ClassVar[str] = "update_config"
    params_class: ClassVar[type[BaseToolParams]] = UpdateConfigParams

    def execute(self, session, args_json: str):
        params = self.parse_params(args_json)
        trial_dir = Path(params.trial_dir).absolute()
        cfg_path = trial_dir / "config.yaml"
        cfg = yaml.safe_load(cfg_path.read_text(encoding="utf-8"))

        for k, v in params.overrides.items():
            _set_nested(cfg, k, v)

        cfg_path.write_text(yaml.safe_dump(cfg, sort_keys=False, allow_unicode=True), encoding="utf-8")
        return json.dumps({"updated": params.overrides}, ensure_ascii=False), {"config": str(cfg_path)}


class RunTrialParams(BaseToolParams):
    name: ClassVar[str] = "run_trial"
    trial_dir: str
    timeout_sec: int = 600


class RunTrialTool(BaseTool):
    name: ClassVar[str] = "run_trial"
    params_class: ClassVar[type[BaseToolParams]] = RunTrialParams

    def execute(self, session, args_json: str):
        params = self.parse_params(args_json)
        trial_dir = Path(params.trial_dir).absolute()
        (trial_dir / "logs").mkdir(exist_ok=True)

        start = time.time()
        env_bin = "/home/ubuntu/.conda/envs/bio_env/bin"
        cmd = f"cd {shlex_quote(str(trial_dir))} && export PATH={shlex_quote(env_bin)}:$PATH && python run_pipeline.py"
        result = session.exec_bash(cmd, timeout=params.timeout_sec)
        elapsed = time.time() - start

        stdout_path = trial_dir / "logs" / "pipeline_stdout.txt"
        stderr_path = trial_dir / "logs" / "pipeline_stderr.txt"
        stamp = time.strftime("%Y-%m-%d %H:%M:%S")
        stdout_block = f"\n\n=== RUN {stamp} ===\n" + (result.get("stdout", "") or "")
        stderr_block = f"\n\n=== RUN {stamp} ===\n" + (result.get("stderr", "") or "")
        stdout_path.write_text((stdout_path.read_text(encoding="utf-8") if stdout_path.exists() else "") + stdout_block, encoding="utf-8")
        stderr_path.write_text((stderr_path.read_text(encoding="utf-8") if stderr_path.exists() else "") + stderr_block, encoding="utf-8")

        payload = {
            "trial_dir": str(trial_dir),
            "exit_code": result.get("exit_code"),
            "elapsed_sec": elapsed,
            "stdout_path": str(stdout_path),
            "stderr_path": str(stderr_path),
        }
        return json.dumps(payload, ensure_ascii=False), payload


class EvaluateTrialParams(BaseToolParams):
    name: ClassVar[str] = "evaluate_trial"
    trial_dir: str
    pipeline_result_json: str | None = None


class EvaluateTrialTool(BaseTool):
    name: ClassVar[str] = "evaluate_trial"
    params_class: ClassVar[type[BaseToolParams]] = EvaluateTrialParams

    def execute(self, session, args_json: str):
        params = self.parse_params(args_json)
        trial_dir = Path(params.trial_dir).absolute()

        rep_path = trial_dir / "representative.fasta"
        cluster_path = trial_dir / "cluster.tsv"
        r1 = trial_dir / "RuvC-I.hhm"
        r2 = trial_dir / "RuvC-II.hhm"
        r3 = trial_dir / "RuvC-III.hhm"

        rep_count = _count_fasta_records(rep_path) if rep_path.exists() else 0

        cluster_rep_count = 0
        if cluster_path.exists():
            reps = set()
            with cluster_path.open("r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    parts = line.rstrip("\n").split("\t")
                    if parts and parts[0]:
                        reps.add(parts[0])
            cluster_rep_count = len(reps)

        ok = all([p.exists() and p.stat().st_size > 0 for p in [r1, r2, r3]])

        score = rep_count
        if not ok:
            score += 1_000_000

        payload = {
            "trial_dir": str(trial_dir),
            "rep_count": rep_count,
            "cluster_rep_count": cluster_rep_count,
            "hhm_ok": ok,
            "score": score,
        }
        return json.dumps(payload, ensure_ascii=False), payload


class DiagnoseParams(BaseToolParams):
    name: ClassVar[str] = "diagnose_and_patch_config"
    trial_dir: str
    pipeline_result_json: str | None = None


class DiagnoseTool(BaseTool):
    name: ClassVar[str] = "diagnose_and_patch_config"
    params_class: ClassVar[type[BaseToolParams]] = DiagnoseParams

    def execute(self, session, args_json: str):
        params = self.parse_params(args_json)
        trial_dir = Path(params.trial_dir).absolute()
        cfg_path = trial_dir / "config.yaml"
        cfg = yaml.safe_load(cfg_path.read_text(encoding="utf-8"))

        stderr_text = _read_text(trial_dir / "logs" / "pipeline_stderr.txt")

        fixes = {}

        current_threads = _get_nested(cfg, "mafft.threads", 4)
        if isinstance(current_threads, int) and current_threads > 8:
            fixes["mafft.threads"] = 8

        current_iter = _get_nested(cfg, "mafft.max_iterate", 2)
        if isinstance(current_iter, int) and current_iter > 10:
            fixes["mafft.max_iterate"] = 10

        min_seq_id = _get_nested(cfg, "cluster.min_seq_id", 0.7)
        cov = _get_nested(cfg, "cluster.coverage", 0.7)

        if "mmseqs" in stderr_text.lower():
            if isinstance(min_seq_id, (int, float)):
                if float(min_seq_id) > 1.0:
                    fixes["cluster.min_seq_id"] = 0.7
                elif float(min_seq_id) < 0.0:
                    fixes["cluster.min_seq_id"] = 0.7
                else:
                    fixes["cluster.min_seq_id"] = max(0.5, float(min_seq_id) - 0.05)
            if isinstance(cov, (int, float)):
                if float(cov) > 1.0:
                    fixes["cluster.coverage"] = 0.7
                elif float(cov) < 0.0:
                    fixes["cluster.coverage"] = 0.7
                else:
                    fixes["cluster.coverage"] = max(0.5, float(cov) - 0.05)

        if "mafft" in stderr_text.lower() and isinstance(current_iter, (int, float)):
            fixes["mafft.max_iterate"] = min(int(current_iter), 2)
            fixes["mafft.threads"] = min(int(current_threads), 4)

        for k, v in fixes.items():
            _set_nested(cfg, k, v)

        cfg_path.write_text(yaml.safe_dump(cfg, sort_keys=False, allow_unicode=True), encoding="utf-8")

        payload = {"patched": fixes, "stderr_head": stderr_text[:2000]}
        diagnosis_path = trial_dir / "logs" / "diagnosis.json"
        diagnosis_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return json.dumps(payload, ensure_ascii=False), payload


def shlex_quote(s: str) -> str:
    return "'" + s.replace("'", "'\"'\"'") + "'"


def create_pr_excavation_tools():
    return [
        CreateTrialTool(),
        UpdateConfigTool(),
        RunTrialTool(),
        EvaluateTrialTool(),
        DiagnoseTool(),
    ]
