import json
from datetime import datetime
from pathlib import Path

from evomaster.agent.session import LocalSession, LocalSessionConfig
from evomaster.agent.tools import create_default_registry
from evomaster.core.exp import extract_agent_response
from evomaster.utils.types import TaskInstance

from .deterministic_llm import DeterministicLLM
from .simple_agents import SimpleAgent
from .tools import create_pr_excavation_tools


def _parse_agent_json_from_content(trajectory) -> dict:
    dialogs = getattr(trajectory, "dialogs", [])
    if not dialogs:
        return {}
    last_dialog = dialogs[-1]
    for msg in reversed(getattr(last_dialog, "messages", [])):
        if getattr(msg, "role", None) and msg.role.value == "assistant":
            if isinstance(msg.content, str) and msg.content.strip():
                try:
                    return json.loads(msg.content)
                except Exception:
                    return {"raw": msg.content}
    return {}


def _parse_agent_json_from_finish(trajectory) -> dict:
    msg = extract_agent_response(trajectory)
    if not msg:
        return {}
    try:
        return json.loads(msg)
    except Exception:
        return {"raw": msg}


def _ensure_dir(p: Path):
    p.mkdir(parents=True, exist_ok=True)


def run_demo(project_dir: str | Path, sample_n: int = 50) -> str:
    project_dir = Path(project_dir).absolute()
    run_root = project_dir / "evomaster_runs"
    run_id = datetime.now().strftime("run_%Y%m%d_%H%M%S")
    run_dir = run_root / run_id
    _ensure_dir(run_dir)
    _ensure_dir(run_dir / "trials")

    session = LocalSession(
        LocalSessionConfig(
            workspace_path=str(run_dir),
            working_dir=str(project_dir),
            timeout=1800,
        )
    )
    session.open()

    tools = create_default_registry()
    tools.register_many(create_pr_excavation_tools())

    planner = SimpleAgent(
        llm=DeterministicLLM("planner"),
        session=session,
        tools=tools,
        config=None,
        skill_registry=None,
        enable_tools=False,
        system_prompt="You are a planner. Output JSON plan only.",
        agent_name="planner",
        config_dir=str(project_dir),
    )
    runner = SimpleAgent(
        llm=DeterministicLLM("runner"),
        session=session,
        tools=tools,
        config=None,
        skill_registry=None,
        enable_tools=True,
        system_prompt="You are a runner. Use tools to run trial.",
        agent_name="runner",
        config_dir=str(project_dir),
    )
    diagnoser = SimpleAgent(
        llm=DeterministicLLM("diagnoser"),
        session=session,
        tools=tools,
        config=None,
        skill_registry=None,
        enable_tools=True,
        system_prompt="You are a diagnoser. Patch config based on failure.",
        agent_name="diagnoser",
        config_dir=str(project_dir),
    )
    reviewer = SimpleAgent(
        llm=DeterministicLLM("reviewer"),
        session=session,
        tools=tools,
        config=None,
        skill_registry=None,
        enable_tools=True,
        system_prompt="You are a reviewer. Evaluate trial outputs.",
        agent_name="reviewer",
        config_dir=str(project_dir),
    )
    optimizer = SimpleAgent(
        llm=DeterministicLLM("optimizer"),
        session=session,
        tools=tools,
        config=None,
        skill_registry=None,
        enable_tools=False,
        system_prompt="You are an optimizer. Output JSON only.",
        agent_name="optimizer",
        config_dir=str(project_dir),
    )

    plan_traj = planner.run(TaskInstance(task_id="planner", task_type="planning", description=json.dumps({"request": "plan"})))
    plan = _parse_agent_json_from_content(plan_traj)

    results = []

    base_overrides = {
        "mafft.threads": 4,
        "mafft.max_iterate": 2,
        "split.min_domain_len": 30,
        "split.window_size": 9,
    }

    sweep = plan.get("sweep", [])
    for i, overrides in enumerate(sweep, start=1):
        trial_id = f"sweep_{i:02d}"
        obs, _ = tools.get_tool("create_trial").execute(
            session,
            json.dumps(
                {"run_dir": str(run_dir), "trial_id": trial_id, "sample_n": sample_n, "source_fasta": "cas12p_1_psiblast.fas"},
                ensure_ascii=False,
            ),
        )
        trial_info = json.loads(obs)
        trial_dir = trial_info["trial_dir"]

        merged = dict(base_overrides)
        merged.update(overrides)
        tools.get_tool("update_config").execute(
            session, json.dumps({"trial_dir": trial_dir, "overrides": merged}, ensure_ascii=False)
        )

        run_task = TaskInstance(
            task_id=f"runner_{trial_id}",
            task_type="run",
            description=json.dumps({"trial_dir": trial_dir, "timeout_sec": 900}, ensure_ascii=False),
        )
        run_traj = runner.run(run_task)
        run_payload = _parse_agent_json_from_finish(run_traj)

        diag_payload = None
        if run_payload.get("exit_code") not in (0, "0"):
            diag_task = TaskInstance(
                task_id=f"diagnose_{trial_id}",
                task_type="diagnose",
                description=json.dumps({"trial_dir": trial_dir}, ensure_ascii=False),
            )
            diag_traj = diagnoser.run(diag_task)
            diag_payload = _parse_agent_json_from_finish(diag_traj)
            patched = (diag_payload or {}).get("patched") or {}
            if isinstance(patched, dict):
                merged.update(patched)
            run_traj = runner.run(TaskInstance(task_id=f"{run_task.task_id}_rerun", task_type="run", description=run_task.description))
            run_payload = _parse_agent_json_from_finish(run_traj)

        eval_task = TaskInstance(
            task_id=f"review_{trial_id}",
            task_type="review",
            description=json.dumps({"trial_dir": trial_dir, "pipeline_result_json": json.dumps(run_payload, ensure_ascii=False)}, ensure_ascii=False),
        )
        eval_traj = reviewer.run(eval_task)
        eval_payload = _parse_agent_json_from_finish(eval_traj)

        results.append(
            {
                "trial_id": trial_id,
                "trial_dir": trial_dir,
                "overrides": merged,
                "diagnosis": diag_payload,
                "metrics": eval_payload,
            }
        )

    best = None
    for r in results:
        score = r.get("metrics", {}).get("score")
        if best is None or (isinstance(score, (int, float)) and score < best.get("metrics", {}).get("score", 1e18)):
            best = r

    opt_plan = _parse_agent_json_from_content(optimizer.run(TaskInstance(task_id="optimizer", task_type="opt", description=json.dumps({"request": "opt"}))))
    neighbors = opt_plan.get("optimize", {}).get("neighbors", [])
    max_rounds = int(opt_plan.get("optimize", {}).get("max_rounds", 0))

    if best and max_rounds > 0:
        current = best
        for ridx in range(1, max_rounds + 1):
            for nidx, delta in enumerate(neighbors, start=1):
                trial_id = f"opt_{ridx:02d}_{nidx:02d}"
                obs, _ = tools.get_tool("create_trial").execute(
                    session,
                    json.dumps(
                        {"run_dir": str(run_dir), "trial_id": trial_id, "sample_n": sample_n, "source_fasta": "cas12p_1_psiblast.fas"},
                        ensure_ascii=False,
                    ),
                )
                trial_info = json.loads(obs)
                trial_dir = trial_info["trial_dir"]

                merged = dict(current["overrides"])
                for k, dv in delta.items():
                    base_v = merged.get(k)
                    if isinstance(base_v, (int, float)) and isinstance(dv, (int, float)):
                        merged[k] = float(base_v) + float(dv)
                tools.get_tool("update_config").execute(
                    session, json.dumps({"trial_dir": trial_dir, "overrides": merged}, ensure_ascii=False)
                )

                run_task_desc = json.dumps({"trial_dir": trial_dir, "timeout_sec": 900}, ensure_ascii=False)
                run_traj = runner.run(TaskInstance(task_id=f"runner_{trial_id}", task_type="run", description=run_task_desc))
                run_payload = _parse_agent_json_from_finish(run_traj)
                if run_payload.get("exit_code") not in (0, "0"):
                    diag_traj = diagnoser.run(TaskInstance(task_id=f"diagnose_{trial_id}", task_type="diagnose", description=json.dumps({"trial_dir": trial_dir}, ensure_ascii=False)))
                    diag_payload = _parse_agent_json_from_finish(diag_traj)
                    patched = (diag_payload or {}).get("patched") or {}
                    if isinstance(patched, dict):
                        merged.update(patched)
                    run_traj = runner.run(TaskInstance(task_id=f"runner_{trial_id}_rerun", task_type="run", description=run_task_desc))
                    run_payload = _parse_agent_json_from_finish(run_traj)
                eval_task_desc = json.dumps({"trial_dir": trial_dir, "pipeline_result_json": json.dumps(run_payload, ensure_ascii=False)}, ensure_ascii=False)
                eval_traj = reviewer.run(TaskInstance(task_id=f"review_{trial_id}", task_type="review", description=eval_task_desc))
                eval_payload = _parse_agent_json_from_finish(eval_traj)
                cand = {"trial_id": trial_id, "trial_dir": trial_dir, "overrides": merged, "metrics": eval_payload}
                results.append(cand)
                if cand["metrics"].get("score", 1e18) < current["metrics"].get("score", 1e18):
                    current = cand

    (run_dir / "summary.json").write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    report_lines = []
    report_lines.append(f"run_dir: {run_dir}")
    for r in results:
        report_lines.append(
            json.dumps(
                {
                    "trial_id": r["trial_id"],
                    "rep_count": r.get("metrics", {}).get("rep_count"),
                    "score": r.get("metrics", {}).get("score"),
                    "overrides": r["overrides"],
                },
                ensure_ascii=False,
            )
        )
    (run_dir / "report.txt").write_text("\n".join(report_lines) + "\n", encoding="utf-8")

    session.close()
    return str(run_dir)


if __name__ == "__main__":
    print(run_demo(Path.cwd()))
