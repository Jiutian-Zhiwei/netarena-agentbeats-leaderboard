"""NetArena app-malt purple agent — A2A server with a zero-LLM code generator.

Replaces the LiteLLM baseline with the deterministic `malt_engine` decision core.
Same A2A surface, no LLM call.

Run:
    python malt_purple_agent.py --host 0.0.0.0 --port 8080
"""

import argparse

import uvicorn

from a2a.server.apps import A2AStarletteApplication
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.tasks import InMemoryTaskStore
from a2a.types import AgentCapabilities, AgentCard, AgentSkill
from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.utils import new_agent_text_message

from malt_engine import decide_from_prompt


class RuleAgent:
    async def invoke(self, input_text: str) -> str:
        return decide_from_prompt(input_text)


class RuleAgentExecutor(AgentExecutor):
    def __init__(self, agent: RuleAgent):
        self.agent = agent

    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        input_text = context.get_user_input()
        result = await self.agent.invoke(input_text)
        await event_queue.enqueue_event(new_agent_text_message(result))

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        raise Exception("cancel not supported")


def parse_args():
    p = argparse.ArgumentParser(description="NetArena malt purple agent (rule engine) as an A2A server.")
    p.add_argument("--host", type=str, default="0.0.0.0")
    p.add_argument("--port", type=int, default=8080)
    p.add_argument("--card-url", type=str, default=None)
    return p.parse_args()


def main():
    args = parse_args()
    server_url = args.card_url or f"http://{args.host}:{args.port}/"

    skill = AgentSkill(
        id="netarena_malt_rule",
        name="NetArena MALT Capacity Planning Rule Agent",
        description="Deterministic graph-query code generator (no LLM).",
        tags=["kubernetes", "graph", "capacity-planning", "rule", "text"],
    )
    card = AgentCard(
        name="NetArena MALT Purple Agent",
        description="Zero-LLM deterministic datacenter capacity planning agent.",
        url=server_url,
        version="1.0.0",
        default_input_modes=["text"],
        default_output_modes=["text"],
        capabilities=AgentCapabilities(streaming=True),
        skills=[skill],
    )

    request_handler = DefaultRequestHandler(
        agent_executor=RuleAgentExecutor(RuleAgent()),
        task_store=InMemoryTaskStore(),
    )
    server = A2AStarletteApplication(agent_card=card, http_handler=request_handler)
    uvicorn.run(server.build(), host=args.host, port=args.port)


if __name__ == "__main__":
    main()
