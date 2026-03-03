import json
import uuid

from evomaster.utils.types import AssistantMessage, FunctionCall, ToolCall


class DeterministicLLM:
    def __init__(self, role: str):
        self.role = role

    def query(self, dialog, **kwargs):
        last_role = dialog.messages[-1].role.value if dialog.messages else ""

        if self.role in {"planner", "optimizer"}:
            if last_role != "user":
                return AssistantMessage(content=" ")
            payload = self._build_plan(dialog.messages[-1].content or "")
            return AssistantMessage(content=json.dumps(payload, ensure_ascii=False))

        if self.role == "runner":
            return self._runner_reply(dialog)
        if self.role == "reviewer":
            return self._reviewer_reply(dialog)
        if self.role == "diagnoser":
            return self._diagnoser_reply(dialog)

        return AssistantMessage(content=" ")

    def _runner_reply(self, dialog):
        if not dialog.messages:
            return AssistantMessage(content=" ")
        last = dialog.messages[-1]
        if last.role.value == "user":
            spec = self._safe_json(last.content)
            tool_call = self._tool_call(
                "run_trial",
                {
                    "trial_dir": spec["trial_dir"],
                    "timeout_sec": spec.get("timeout_sec", 600),
                },
            )
            return AssistantMessage(content=" ", tool_calls=[tool_call])
        if last.role.value == "tool" and getattr(last, "name", "") == "run_trial":
            tool_call = self._tool_call(
                "finish",
                {
                    "message": last.content or "",
                    "task_completed": "true",
                },
            )
            return AssistantMessage(content=" ", tool_calls=[tool_call])
        return AssistantMessage(content=" ")

    def _reviewer_reply(self, dialog):
        if not dialog.messages:
            return AssistantMessage(content=" ")
        last = dialog.messages[-1]
        if last.role.value == "user":
            spec = self._safe_json(last.content)
            tool_call = self._tool_call(
                "evaluate_trial",
                {
                    "trial_dir": spec["trial_dir"],
                    "pipeline_result_json": spec.get("pipeline_result_json"),
                },
            )
            return AssistantMessage(content=" ", tool_calls=[tool_call])
        if last.role.value == "tool" and getattr(last, "name", "") == "evaluate_trial":
            tool_call = self._tool_call(
                "finish",
                {
                    "message": last.content or "",
                    "task_completed": "true",
                },
            )
            return AssistantMessage(content=" ", tool_calls=[tool_call])
        return AssistantMessage(content=" ")

    def _diagnoser_reply(self, dialog):
        if not dialog.messages:
            return AssistantMessage(content=" ")
        last = dialog.messages[-1]
        if last.role.value == "user":
            spec = self._safe_json(last.content)
            tool_call = self._tool_call(
                "diagnose_and_patch_config",
                {
                    "trial_dir": spec["trial_dir"],
                    "pipeline_result_json": spec.get("pipeline_result_json"),
                },
            )
            return AssistantMessage(content=" ", tool_calls=[tool_call])
        if last.role.value == "tool" and getattr(last, "name", "") == "diagnose_and_patch_config":
            tool_call = self._tool_call(
                "finish",
                {
                    "message": last.content or "",
                    "task_completed": "true",
                },
            )
            return AssistantMessage(content=" ", tool_calls=[tool_call])
        return AssistantMessage(content=" ")

    def _build_plan(self, user_content: str):
        _ = user_content
        return {
            "sweep": [
                {"filter.min_length": 120, "cluster.min_seq_id": 1.2, "cluster.coverage": 0.6},
                {"filter.min_length": 120, "cluster.min_seq_id": 0.65, "cluster.coverage": 0.6},
                {"filter.min_length": 150, "cluster.min_seq_id": 0.7, "cluster.coverage": 0.7},
                {"filter.min_length": 180, "cluster.min_seq_id": 0.75, "cluster.coverage": 0.7},
            ],
            "optimize": {
                "max_rounds": 2,
                "neighbors": [
                    {"cluster.min_seq_id": -0.05},
                    {"cluster.min_seq_id": 0.05},
                    {"cluster.coverage": -0.05},
                    {"cluster.coverage": 0.05},
                ],
            },
        }

    def _tool_call(self, name: str, args: dict):
        return ToolCall(
            id=str(uuid.uuid4()),
            function=FunctionCall(name=name, arguments=json.dumps(args, ensure_ascii=False)),
        )

    def _safe_json(self, s):
        if isinstance(s, list):
            s = " ".join([b.get("text", "") if isinstance(b, dict) else str(b) for b in s])
        if not s:
            return {}
        try:
            return json.loads(s)
        except Exception:
            return {"raw": s}
