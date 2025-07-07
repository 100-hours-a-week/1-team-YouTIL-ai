from langchain_core.tools import BaseTool
from tavily import AsyncTavilyClient
from langchain_core.tools import tool
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import InjectedToolArg
from typing import List, Annotated, Literal, cast
from langsmith import traceable

from utils import get_config_value
from config import MultiAgentConfiguration
from prompt import RESEARCH_INSTRUCTIONS
from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, START, END


from agent_schema import (
    ReportState, 
    CommitReportSchema,
    SectionWriterInput,
    ReportOutputState,
    FinishResearch
)

import asyncio

@traceable
async def tavily_search_async(search_queries, max_results: int = 5, topic: Literal["general", "news", "finance"] = "general", include_raw_content: bool = True):
    """
    Tavily API를 사용하여 동시 웹 검색을 수행합니다.

    Args:
        search_queries (List[str]): 처리할 검색 쿼리 목록
        max_results (int): 반환할 최대 결과 수
        topic (Literal["general", "news", "finance"]): 결과를 필터링할 주제
        include_raw_content (bool): 결과에 원시 콘텐츠를 포함할지 여부

    Returns:
            List[dict]: Tavily API에서 반환된 검색 응답 목록:
                {
                    'query': str,
                    'follow_up_questions': None,      
                    'answer': None,
                    'images': list,
                    'results': [                     # 검색 결과 목록
                        {
                            'title': str,            # 웹페이지 제목
                            'url': str,              # 결과 URL
                            'content': str,          # 요약/스니펫 콘텐츠
                            'score': float,          # 관련성 점수
                            'raw_content': str|None  # 전체 페이지 콘텐츠(사용 가능한 경우)
                        },
                        ...
                    ]
                }
    """
    tavily_async_client = AsyncTavilyClient()
    search_tasks = []
    for query in search_queries:
            search_tasks.append(
                tavily_async_client.search(
                    query,
                    max_results=max_results,
                    include_raw_content=include_raw_content,
                    topic=topic
                )
            )
            # 1초 대기
            await asyncio.sleep(1)

    # Execute all searches concurrently
    search_docs = await asyncio.gather(*search_tasks)
    return search_docs

TAVILY_SEARCH_DESCRIPTION = (
        "종합적이고 정확하고 신뢰할 수 있는 결과를 위해 최적화된 검색 엔진입니다. "
        "현재 이벤트에 대한 질문에 답하는 데 유용합니다."
)


@tool(description=TAVILY_SEARCH_DESCRIPTION)
async def tavily_search(
    queries: List[str],
    max_results: Annotated[int, InjectedToolArg] = 5,
    topic: Annotated[Literal["general", "news", "finance"], InjectedToolArg] = "general",
    config: RunnableConfig = None
) -> str:
    """
    Tavily 검색 API에서 결과를 가져옵니다.
    """
    search_results = await tavily_search_async(
        search_queries=queries,
        max_results=max_results,
        topic=topic,
        include_raw_content=True
    )

    # Format the search results directly using the raw_content already provided
    formatted_output = "검색 결과:\n\n"
    
    unique_results = {}
    for response in search_results:
        for result in response['results']:
            url = result['url']
            if url not in unique_results:
                unique_results[url] = {**result, "query": response['query']}

    for url, result in unique_results.items():
        formatted_output += f"- **{result['title']}**\n  {url}\n  {result['content'][:1000]}...\n\n"

    return formatted_output


async def get_search_tool(search_api: str) -> BaseTool:
    """configuration에 기반한 도구 호출하기"""

    config = RunnableConfig()
    configurable = MultiAgentConfiguration.from_runnable_config(config)
    search_api = get_config_value(configurable.search_api)

    # Return None if no search tool is requested
    # if search_api.lower() == "none":
    #     return None

    # TODO: Configure other search functions as tools
    if search_api.lower() == "tavily":
        search_tool = tavily_search
    else:
        raise NotImplementedError(
            f"The search API '{search_api}' is not yet supported in the multi-agent implementation. "
            f"Currently, only Tavily/DuckDuckGo/None is supported. Please use the graph-based implementation in "
            f"src/open_deep_research/graph.py for other search APIs, or set search_api to 'tavily', 'duckduckgo', or 'none'."
        )

    tool_metadata = {**(search_tool.metadata or {}), "type": "search"}
    search_tool.metadata = tool_metadata
    return search_tool


async def get_research_tools(config: RunnableConfig) -> list[BaseTool]:
    config = RunnableConfig()
    """configuration에 기반한 도구 호출하기"""
    search_tool = await get_search_tool(config)
    tools = [tool(SectionWriterInput), tool(CommitReportSchema), tool(FinishResearch)]
    if search_tool is not None:
        tools.append(search_tool)  # Add search tool, if available
    # existing_tool_names = {cast(BaseTool, tool).name for tool in tools}
    return tools

async def research_agent(state: ReportState, config: RunnableConfig):
    """LLM이 도구를 호출할지 여부를 결정합니다"""
    commit_analysis_result = state["section"]
    
    # Get configuration
    configurable = MultiAgentConfiguration.from_runnable_config(config)
    researcher_model = get_config_value(configurable.researcher_model)
    
    # Initialize the model
    llm = ChatOpenAI(model=researcher_model, temperature=0)

    # Get tools based on configuration
    research_tool_list = await get_research_tools(config)
    system_prompt = RESEARCH_INSTRUCTIONS.format(
        code_review=commit_analysis_result["code_review"],
        number_of_query=configurable.number_of_queries,
    )
    # if configurable.mcp_prompt:
    #     system_prompt += f"\n\n{configurable.mcp_prompt}"

    # Ensure we have at least one user message (required by Anthropic)
    messages = state.get("messages", [])
    if not messages:
        messages = [{"role": "user", "content": f"커밋 내용에 대한 웹검색을 수행하고 보고서를 작성해 주세요: {commit_analysis_result['code_review']}"}]


    return {
        "messages": [
            # Enforce tool calling to either perform more search or call the Section tool to write the section
            await llm.bind_tools(research_tool_list,             
                                 parallel_tool_calls=False,
                                 # force at least one tool call
                                 tool_choice="any").ainvoke(
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

async def research_agent_tools(state: ReportState, config: RunnableConfig):
    """도구 호출을 수행하고 에이전트에게 전달하거나 연구 루프를 지속합니다"""
    configurable = MultiAgentConfiguration.from_runnable_config(config)

    result = []
    completed_section = None
    source_str = ""
    
    # Get tools based on configuration
    research_tool_list = await get_research_tools(config)
    research_tools_by_name = {tool.name: tool for tool in research_tool_list}
    search_tool_names = {
        tool.name
        for tool in research_tool_list
        if tool.metadata is not None and tool.metadata.get("type") == "search"
    }
    
    # Process all tool calls first (required for OpenAI)
    for tool_call in state["messages"][-1].tool_calls:
        # Get the tool
        tool = research_tools_by_name[tool_call["name"]]
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
        
        # Store the section observation if a Section tool was called
        if tool_call["name"] == "CommitReportSchema":
            completed_section = cast(CommitReportSchema, observation)


        # Store the source string if a search tool was called
        if tool_call["name"] in search_tool_names and configurable.include_source_str:
            source_str += cast(str, observation)
    
    # After processing all tools, decide what to do next
    state_update = {"messages": result}
    if completed_section:
        # Write the completed section to state and return to the supervisor
        state_update["completed_sections"] = [completed_section]
    if configurable.include_source_str and source_str:
        state_update["source_str"] = source_str

    return state_update

async def research_agent_should_continue(state: ReportState) -> str:
    """LM이 도구 호출을 했는지 여부에 따라 루프를 계속할지 중지할지 결정합니다."""

    messages = state["messages"]
    last_message = messages[-1]

    if last_message.tool_calls[0]["name"] == "FinishResearch":
        # Research is done - return to supervisor
        return END
    else:
        return "research_agent_tools"
    

research_builder = StateGraph(ReportState, output=ReportOutputState, config_schema=MultiAgentConfiguration)
research_builder.add_node("research_agent", research_agent)
research_builder.add_node("research_agent_tools", research_agent_tools)
research_builder.add_edge(START, "research_agent") 
research_builder.add_conditional_edges(
    "research_agent",
    research_agent_should_continue,
    ["research_agent_tools", END]
)
research_builder.add_edge("research_agent_tools", "research_agent")

research_builder = research_builder.compile()