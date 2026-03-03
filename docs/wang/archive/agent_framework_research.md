# Task Agent Framework Research

## Executive summary

If **latency is the top priority**, the best fit is:

1. **Build our own minimal event-driven tool loop on the raw provider SDK**
2. **Use PydanticAI only if we want a thin typed wrapper around tools/deps/streaming**
3. **Avoid heavier orchestration frameworks for the Task Agent hot path**

My recommendation is:

- **Primary recommendation**: build a custom Task Agent runtime in Python on top of the **Anthropic Python SDK** or **OpenAI Python SDK**
- **Best framework fallback**: **PydanticAI**, if we want typed dependencies, tool registration, and streaming helpers without committing to a workflow runtime
- **Do not use** LangGraph / AutoGen Core / CrewAI as the main Task Agent implementation unless our scope expands materially beyond the current design
- **Do not use Claude Agent SDK for this path** unless we intentionally want Claude Code’s full agent loop and tool environment

The key reason is simple:

**Our Task Agent is not a generic autonomous agent. It is an event-driven supervisory controller with narrow tools and strict latency expectations.**

That shape does not need a workflow engine.

## 1. What we actually need

The Task Agent pattern in `design.md` is:

1. receive external event (`ExpertSignal`, `WorldModel` event, task start)
2. inject a structured context packet / blackboard snapshot
3. run one LLM decision turn
4. possibly execute one or more narrow tools
5. persist updated state
6. go back to sleep until the next event

This is **not**:

- a persistent ReAct chat loop
- a multi-agent conversation runtime
- a DAG orchestration engine
- a human-approval workflow platform
- a code-agent environment with file editing and shell tooling

## 2. Framework ranking

### Recommended order

1. **Custom minimal loop on raw SDK**
2. **PydanticAI**
3. **OpenAI Agents SDK** as a secondary alternative
4. **LangGraph**
5. **AutoGen Core**
6. **Claude Agent SDK**
7. **CrewAI**

## 3. Comparison table

| Option | Latency | Event-driven | Structured state injection | Parallel 5-10 tasks | Complexity | Verdict |
|---|---|---|---|---|---|---|
| Raw OpenAI / Anthropic SDK | Best | Build ourselves, easy | Best, fully custom | Best | Low-moderate | **Best fit** |
| PydanticAI | Very good | Outer loop stays ours | Very good via typed deps | Good | Low-moderate | **Best framework** |
| OpenAI Agents SDK | Good | Possible | Good via context + sessions | Good | Moderate | Viable, but more than needed |
| LangGraph | Acceptable | Good via interrupts/resume | Strong | Good | Medium-high | Overbuilt for current scope |
| AutoGen Core | Acceptable | Excellent | Reasonable | Good | High | Elegant but too heavy |
| Claude Agent SDK | Weak for us | Partial | Session-oriented | Possible | High | Wrong shape |
| CrewAI | Weak | Good on paper | Good | Fine | High | Workflow framework, not substrate |

## 4. Raw OpenAI / Anthropic SDK

### Why it fits best

- lowest wrapper overhead
- direct streaming access
- direct tool-call handling
- no framework-imposed loop model
- easiest to implement `sleep until event`
- easiest to share a single async client across many Task Agents

### Official references

- OpenAI streaming responses: https://developers.openai.com/api/docs/guides/streaming-responses
- OpenAI Python SDK: https://github.com/openai/openai-python
- Anthropic streaming API: https://docs.anthropic.com/en/api/messages-streaming
- Anthropic Python SDK: https://github.com/anthropics/anthropic-sdk-python
- Anthropic tool definition: https://platform.claude.com/docs/en/agents-and-tools/tool-use/define-tools

### Latency assessment

**Best option.**

Inference from the official docs and SDK shape:

- there is no graph runtime, actor runtime, or workflow engine in front of the provider call
- first-action latency is dominated by provider inference + network + our own tool execution
- we control whether we stop after the first actionable tool call or keep the reasoning turn going

### Event-driven capability

**Excellent**, because we can model it exactly:

- one `asyncio.Queue` per task
- `await queue.get()` to sleep
- wake on `ExpertSignal` / `WorldModel` event / task start
- run one LLM turn
- sleep again

### State management

**Excellent, but fully ours**

That is a feature here, not a bug. We can keep:

- task blackboard
- recent event ring buffer
- open decisions
- latest expert summary
- last decision metadata

outside the conversation transcript.

### Parallelism

**Excellent**

Recommended shape:

```python
client = AsyncAnthropic()  # or AsyncOpenAI()
task_agents = {task_id: TaskAgentRuntime(client, ...)}
```

One shared async client per process is the cleanest way to support 5-10 Task Agents without separate API clients.

### Example Task Agent shape

```python
@dataclass
class TaskState:
    task_id: str
    blackboard: dict
    recent_events: list[dict]
    autonomy_mode: str


class TaskAgentRuntime:
    def __init__(self, client, model: str, tools: dict[str, Callable]):
        self.client = client
        self.model = model
        self.tools = tools
        self.queue: asyncio.Queue[dict] = asyncio.Queue()

    async def push_event(self, event: dict) -> None:
        await self.queue.put(event)

    async def run(self, state: TaskState) -> None:
        while True:
            event = await self.queue.get()
            packet = build_context_packet(state, event)
            response = await self.client.messages.create(
                model=self.model,
                system=TASK_AGENT_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": json.dumps(packet)}],
                tools=TASK_AGENT_TOOLS,
                max_tokens=800,
            )

            while True:
                tool_uses = extract_tool_calls(response)
                if not tool_uses:
                    apply_brain_output(state, response)
                    break

                tool_results = []
                for call in tool_uses:
                    result = await self.tools[call.name](**call.input)
                    tool_results.append(format_tool_result(call, result))

                response = await self.client.messages.create(
                    model=self.model,
                    system=TASK_AGENT_SYSTEM_PROMPT,
                    messages=continue_messages(packet, response, tool_results),
                    tools=TASK_AGENT_TOOLS,
                    max_tokens=800,
                )
```

### Custom code estimate

A practical first version is realistically small:

- ~150-250 lines for the core event-driven loop
- ~100-200 lines for tool registry + dispatch
- ~100-150 lines for task state store + packet serialization

## 5. Claude Agent SDK

### Official references

- overview: https://platform.claude.com/docs/en/agent-sdk/overview
- Python SDK: https://platform.claude.com/docs/en/agent-sdk/python
- agent loop: https://platform.claude.com/docs/en/agent-sdk/agent-loop
- hooks: https://platform.claude.com/docs/en/agent-sdk/hooks
- sessions: https://platform.claude.com/docs/en/agent-sdk/sessions
- Python repo: https://github.com/anthropics/claude-agent-sdk-python

### What it is good at

It is a strong SDK for the Claude Code style of agent:

- sessions
- hooks
- subagents
- built-in and custom tools
- in-process MCP tool servers

The repo README explicitly says the package bundles the Claude Code CLI and exposes `query()` plus `ClaudeSDKClient`.

### Why it is a bad fit for us

- optimized around the Claude Code agent loop, not a tiny supervisory turn
- carries tool-runtime assumptions we do not want
- session model is conversation-centric, not blackboard-centric
- likely worse first-action latency than the raw Anthropic SDK because there is more machinery in the loop

### Example shape

```python
async with ClaudeSDKClient(options=options) as client:
    await client.query(render_task_event_prompt(packet))
    async for msg in client.receive_response():
        handle_sdk_message(msg)
```

This works, but it is solving a larger problem than ours.

### Verdict

**Not recommended for Task Agent implementation.**

## 6. LangGraph

### Official references

- overview: https://docs.langchain.com/oss/python/langgraph
- streaming: https://docs.langchain.com/oss/python/langgraph/streaming
- interrupts: https://docs.langchain.com/oss/python/langgraph/interrupts
- memory: https://docs.langchain.com/oss/python/langgraph/memory

### Strengths

- strong state/checkpoint model
- good interrupt / resume semantics
- useful for long-running durable workflows

### Weaknesses for our use case

- graph runtime is heavier than the problem demands
- “wake on event -> do one turn -> sleep” becomes a graph/resume problem
- more runtime/state machinery than we need on the hot path

### Example shape

```python
class TaskState(TypedDict):
    task: dict
    packet: dict
    latest_signal: dict | None
    pending_actions: list[dict]


def brain_node(state: TaskState):
    decision = llm_with_tools.invoke(render_packet(state["packet"]))
    return {"pending_actions": extract_actions(decision)}


graph = StateGraph(TaskState)
graph.add_node("brain", brain_node)
graph = graph.compile(checkpointer=checkpointer)

graph.invoke(
    {"latest_signal": signal, "packet": packet},
    config={"configurable": {"thread_id": task_id}},
)
```

### Verdict

**Technically capable, but overbuilt for the current Task Agent.**

## 7. AutoGen Core

### Official references

- core guide: https://microsoft.github.io/autogen/stable/user-guide/core-user-guide/index.html
- agent/runtime: https://microsoft.github.io/autogen/stable/user-guide/core-user-guide/framework/agent-and-agent-runtime.html
- topics/subscriptions: https://microsoft.github.io/autogen/0.4.6/user-guide/core-user-guide/core-concepts/topic-and-subscription.html
- distributed runtime: https://microsoft.github.io/autogen/dev/user-guide/core-user-guide/framework/distributed-agent-runtime.html

### Strengths

- event-driven semantics are excellent
- topic/subscription maps cleanly to `task/<task_id>`
- runtime-managed agents are a good conceptual match for event routing

### Weaknesses

- too much runtime abstraction for one supervisory brain in one Python process
- higher conceptual and implementation overhead than we need
- docs themselves position Core as flexible but more challenging

### Example shape

```python
@dataclass
class ExpertSignalMsg:
    task_id: str
    packet: dict


class TaskBrain(RoutedAgent):
    def __init__(self, model_client):
        super().__init__("Task brain")
        self.model_client = model_client

    @message_handler
    async def handle_signal(self, message: ExpertSignalMsg, ctx: MessageContext):
        decision = await run_llm_turn(self.model_client, message.packet)
        await dispatch_tool_calls(decision)
```

### Verdict

**Architecturally elegant, operationally too heavy.**

## 8. CrewAI

### Official references

- flows: https://docs.crewai.com/en/concepts/flows
- event listeners: https://docs.crewai.com/en/concepts/event-listener

### Strengths

- structured stateful flows
- event listener system

### Weaknesses

- workflow/crew abstraction is broader than our problem
- more automation framework than Task Agent substrate
- poor fit for latency-first supervisory control

### Verdict

**Not recommended.**

## 9. PydanticAI

### Official references

- overview: https://ai.pydantic.dev/
- dependencies: https://ai.pydantic.dev/dependencies/
- tools: https://ai.pydantic.dev/tools/
- toolsets: https://ai.pydantic.dev/toolsets/
- agent iteration/streaming: https://ai.pydantic.dev/agent/
- graphs: https://ai.pydantic.dev/graph/

### Why it fits well

- Python-native
- typed dependencies map well to our task blackboard and runtime handles
- good streaming hooks
- lower ceremony than LangGraph / AutoGen / CrewAI
- does not force us into a polling loop

The docs explicitly show:

- `run_stream(..., event_stream_handler=...)`
- `run_stream_events()`
- lower-level `Agent.iter`
- dependency injection via `deps_type` and `RunContext.deps`

### Latency

**Second-best after raw SDK**

There is some wrapper overhead, but much less than larger orchestration frameworks.

### State injection

**Very good**

Its typed `deps` model is the cleanest framework-native match to:

- task state
- world facade
- kernel facade
- tool handles

### Example shape

```python
@dataclass
class BrainDeps:
    task_state: TaskState
    world: WorldFacade
    kernel: KernelFacade


brain = Agent(
    "anthropic:claude-sonnet-4-5",
    deps_type=BrainDeps,
    tools=[start_job, patch_job, pause_job, resume_job, abort_job],
)


async def handle_event(event: ExpertSignal, deps: BrainDeps):
    packet = build_context_packet(deps.task_state, event)
    result = await brain.run(
        json.dumps(packet),
        deps=deps,
        message_history=[],
    )
    apply_decision(result.output, deps.task_state)
```

### Verdict

**Best framework option.**

## 10. OpenAI Agents SDK

### Why it is worth mentioning

It was not on the required list, but it is a relevant lightweight alternative.

### Official references

- overview: https://openai.github.io/openai-agents-python/
- agents/context: https://openai.github.io/openai-agents-python/agents/
- streaming: https://openai.github.io/openai-agents-python/streaming/
- sessions: https://openai.github.io/openai-agents-python/sessions/

### Relevant capabilities

- docs say agents can take any Python object as context
- streaming emits raw response events and higher-level run-item events
- sessions support SQLite / Redis / SQLAlchemy / hosted backends

### Why it is still not first choice

- more agent framework than we need
- handoffs/guardrails/sessions go beyond the current Task Agent requirements
- raw SDK or PydanticAI remains simpler

### Verdict

**Viable, but not better than custom loop or PydanticAI.**

## 11. Build-our-own minimal loop on Anthropic SDK

### How hard is it?

**Not hard.**

A solid first version is realistically a **~200 line core loop** plus tool/state plumbing.

### What we must implement

1. `TaskAgentRuntime`
   - owns event queue
   - owns task state
   - wakes on event
2. `ContextPacketBuilder`
   - full packet on task start
   - delta packet on event
   - compressed summary if needed
3. `ToolRegistry`
   - `start_job`
   - `patch_job`
   - `pause_job`
   - `resume_job`
   - `abort_job`
   - `query_world`
   - `request_resource`
4. `DecisionPolicy`
   - max turns
   - stop after first actionable tool call if configured
   - default-if-timeout policy
5. `StateStore`
   - blackboard persistence
   - recent event ring buffer
   - last decision metadata

### What we gain

- lowest latency
- total control over packet format
- exact wake/sleep semantics
- lower dependency surface
- easier profiling and debugging

### What we lose

- no built-in graph UI
- no built-in workflow engine
- no built-in event bus
- no built-in human approval flow

For the current Task Agent, these are acceptable losses.

## 12. Final recommendation

If Wang wants the shortest correct answer:

**Build the Task Agent ourselves on the raw Python SDK.**

Use a tiny event-driven runtime:

- queue event
- build context packet
- run one LLM turn with narrow tools
- execute tools
- persist state
- sleep

If we want some framework help without giving up that shape:

**Use PydanticAI as a thin typed layer, not a workflow engine.**
