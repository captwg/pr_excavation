from evomaster.agent.agent import BaseAgent


class SimpleAgent(BaseAgent):
    VERSION = "0.1"

    def __init__(self, *args, system_prompt: str, agent_name: str, **kwargs):
        super().__init__(*args, **kwargs)
        self._system_prompt = system_prompt
        self._agent_name = agent_name

    def _get_system_prompt(self) -> str:
        return self._system_prompt

    def _get_user_prompt(self, task) -> str:
        return task.description

