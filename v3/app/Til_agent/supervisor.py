import os
import asyncio
from langgraph.graph import END, StateGraph, START
from langchain_core.tools import BaseTool
from langchain_core.runnables import RunnableConfig
from langgraph.types import Command,Send
from .config import MultiAgentConfiguration
from typing import cast, Literal
from langchain_core.tools import tool
from .utils import get_config_value

from langchain_openai import ChatOpenAI
from pydantic import BaseModel
from .agent_schema import (
    CommitDataSchema,
    TilStateOutput,
    Sections,
    Introduction,
    Conclusion,
    FinishReport,
    TilState,
    Concept,
)
from dotenv import load_dotenv
from .utils import kafka_produce
from .prompt import SUPERVISOR_INSTRUCTIONS, INSTRUCTION_WRITER_INSTRUCTIONS
from .research_team_agent import research_builder, get_search_tool
from .commit_analyze_graph import CommitAnalysisGraph

env_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../.env"))
load_dotenv(dotenv_path=env_path)

model = ChatOpenAI(model="gpt-4o-mini", temperature=0,)

async def get_supervisor_tools(config: RunnableConfig) -> list[BaseTool]:
    """Get supervisor tools based on configuration"""
    configurable = MultiAgentConfiguration.from_runnable_config(config)
    search_tool = await get_search_tool(config)
    tools = [tool(Sections), tool(Introduction), tool(Conclusion), tool(FinishReport), tool(Concept)]
    # if search_tool is not None:
    #     tools.append(search_tool)  # Add search tool, if available
    # existing_tool_names = {cast(BaseTool, tool).name for tool in tools}
    # mcp_tools = await _load_mcp_tools(config, existing_tool_names)
    # tools.extend(mcp_tools)
    return tools

async def supervisor(state: TilState, config: RunnableConfig):
    """LLM decides whether to call a tool or not"""

    # Messages
    messages = state["messages"]

    # Get configuration
    configurable = MultiAgentConfiguration.from_runnable_config(config)
    supervisor_model = get_config_value(configurable.supervisor_model)

    # Initialize the model
    llm = ChatOpenAI(model=supervisor_model)

    if state.get("messages") is None:
        kafka_produce(state["kafka_request"], "SUPERVISOR_START")

    
    # If sections have been completed, but we don't yet have the final report, then we need to initiate writing the introduction and conclusion
    if state.get("completed_sections") and not state.get("final_report"):
        research_complete_message = {"role": "user", "content": "연구가 완료되었습니다. 이제 Concept, Introduction, Conclusion을 작성하세요. 완성된 본문 섹션은 다음과 같습니다 \n\n" + "\n\n".join([s.commit_report for s in state["completed_sections"]])}
        messages = messages + [research_complete_message]

    # Get tools based on configuration
    supervisor_tool_list = await get_supervisor_tools(config)
    
    
    llm_with_tools = (
        llm
        .bind_tools(
            supervisor_tool_list,
            parallel_tool_calls=False,
            # force at least one tool call
            tool_choice="any"
        )
    )

    # Get system prompt
    system_prompt = SUPERVISOR_INSTRUCTIONS
    # if configurable.mcp_prompt:
    #     system_prompt += f"\n\n{configurable.mcp_prompt}"

    # Invoke
    return {
        "messages": [
            await llm_with_tools.ainvoke(
                [
                    {
                        "role": "system",
                        "content": system_prompt
                    }
                ]
                + messages
            )
        ]
    }

async def supervisor_tools(state: TilState, config: RunnableConfig)  -> Command[Literal["supervisor", "research_team", "__end__"]]:
    """도구 호출을 수행하고 research_team 에게 전달합니다."""
    configurable = MultiAgentConfiguration.from_runnable_config(config)


    result = []
    sections_list = []
    intro_content = None
    conclusion_content = None
    concept_content = None
    concept_keywords = []
    source_str = ""

    # Get tools based on configuration
    supervisor_tool_list = await get_supervisor_tools(config)
    supervisor_tools_by_name = {tool.name: tool for tool in supervisor_tool_list}
    search_tool_names = {
        tool.name
        for tool in supervisor_tool_list
        if tool.metadata is not None and tool.metadata.get("type") == "search"
    }

    # First process all tool calls to ensure we respond to each one (required for OpenAI)
    for tool_call in state["messages"][-1].tool_calls:
        # Get the tool
        tool = supervisor_tools_by_name[tool_call["name"]]
        # Perform the tool call - use ainvoke for async tools
        try:
            observation = await tool.ainvoke(tool_call["args"], config)
        except NotImplementedError:
            observation = tool.invoke(tool_call["args"], config)

        # Append to messages 
        result.append({"role": "tool", 
                       "content": observation, 
                       "name": tool_call["name"], 
                       "tool_call_id": tool_call["id"]})

        if tool_call["name"] == "Sections":
            # sections_list = cast(Sections, observation).sections
            print("[Sections tool called] Ignored; using state.sections instead.")
        elif tool_call["name"] == "Concept":
            # Format introduction with proper H1 heading if not already formatted
            observation = cast(Concept, observation)
            concept_content = observation.concept
            concept_keywords = observation.keywords
        elif tool_call["name"] == "Introduction":
            # Format introduction with proper H1 heading if not already formatted
            observation = cast(Introduction, observation)
            intro_content = observation.content
        elif tool_call["name"] == "Conclusion":
            # Format conclusion with proper H2 heading if not already formatted
            observation = cast(Conclusion, observation)
            if not observation.content.startswith("## "):
                conclusion_content = f"{observation.content}"
            else:
                conclusion_content = observation.content
        elif tool_call["name"] in search_tool_names and configurable.include_source_str:
            source_str += cast(str, observation)

    # 완료된 filename 목록 만들기
    completed_filenames = {
        os.path.basename(s["filename"] if isinstance(s, dict) else s.filename)
        for s in state.get("completed_sections", [])
    }

    pending_sections = [
        s for s in state["sections"]
        if os.path.basename(s["filename"] if isinstance(s, dict) else s.filename) not in completed_filenames
    ]

    if pending_sections:
        if state["kafka_request"] is not None:
            kafka_produce(state["kafka_request"], "RESEARCH_TEAM_START")
        return Command(
            goto=[
                Send("research_team", {"section": s.dict() if isinstance(s, BaseModel) else s})
                for s in pending_sections
            ],
            update={"messages": result})
    elif concept_content:
        body = "\n\n".join(f"## {s.filename}\n\n{s.commit_report}" for s in state["completed_sections"])
        result.append({"role": "user", "content": INSTRUCTION_WRITER_INSTRUCTIONS.format(body=body)})
        state_update = {
            "concept": concept_content,
            "keywords": concept_keywords,
            "messages": result,
        }
    elif intro_content:
        if state["kafka_request"] is not None:
            kafka_produce(state["kafka_request"], "INTRODUCTION_START")
        # Store introduction while waiting for conclusion
        # Append to messages to guide the LLM to write conclusion next
        result.append({"role": "user", "content": "Introduction 작성이 완료되었습니다. 이제 결론 부분을 작성합니다."})
        state_update = {
            "final_report": intro_content,
            "messages": result,
        }
    elif conclusion_content:
        if state["kafka_request"] is not None:
            kafka_produce(state["kafka_request"], "CONCLUSION_START")
        # Get all sections and combine in proper order: Introduction, Body Sections, Conclusion
        intro = state.get("final_report", "")
        body_sections = "\n\n".join(f"# {s.filename}\n\n{s.commit_report}\n---" for s in state["completed_sections"])
        
        # Assemble final report in correct order
        complete_report = f"# 📅 {state.get('date', '')} TIL\n\n{intro}\n\n{body_sections}\n# 회고\n{conclusion_content}"
        
        # Append to messages to indicate completion
        result.append({"role": "user", "content": "TIL(Today I Leared)의 개요, 본문 섹션, 회고 부분이 작성 완료되었습니다."})

        state_update = {
            "final_report": complete_report,
            "messages": result,
        }
    else:
        # Default case (for search tools, etc.)
        state_update = {"messages": result}

    # Include source string for evaluation
    if configurable.include_source_str and source_str:
        state_update["source_str"] = source_str

    return Command(goto="supervisor", update=state_update)

async def supervisor_should_continue(state: TilState) -> str:
    """LLM이 도구 호출을 했는지 여부에 따라 루프를 계속할지 중지할지 결정합니다"""

    messages = state["messages"]
    last_message = messages[-1]
    # End because the supervisor asked a question or is finished
    if not last_message.tool_calls or (len(last_message.tool_calls) == 1 and last_message.tool_calls[0]["name"] == "FinishReport"):
        # Exit the graph
        return END

    # If the LLM makes a tool call, then perform an action
    return "supervisor_tools"

# Supervisor workflow
class SupervisorGraph:
    def __init__(self, no_files: int):
        self.no_files = no_files
        self.commit_analysis_graph = CommitAnalysisGraph(no_files=no_files).make_commit_analysis_graph()

    async def make_supervisor_graph(self):
        supervisor_builder = StateGraph(input=CommitDataSchema, output=TilStateOutput, config_schema=MultiAgentConfiguration)
        supervisor_builder.add_node("supervisor", supervisor)
        supervisor_builder.add_node("supervisor_tools", supervisor_tools)
        supervisor_builder.add_node("commit_analysis_graph", self.commit_analysis_graph)
        supervisor_builder.add_node("research_team", research_builder)

        # Flow of the supervisor agent
        supervisor_builder.add_edge(START, "commit_analysis_graph")
        supervisor_builder.add_edge("commit_analysis_graph", "supervisor")
        supervisor_builder.add_conditional_edges(
            "supervisor",
            supervisor_should_continue,
            ["supervisor_tools", END]
        )
        supervisor_builder.add_edge("research_team", "supervisor")

        graph = supervisor_builder.compile()

        return graph