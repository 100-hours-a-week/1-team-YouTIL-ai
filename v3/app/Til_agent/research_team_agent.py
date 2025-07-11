from langchain_core.tools import BaseTool
from tavily import AsyncTavilyClient
from langchain_core.tools import tool
from langsmith import traceable
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import InjectedToolArg
from typing import List, Annotated, Literal, cast
from langsmith import traceable

from .utils import get_config_value
from .config import MultiAgentConfiguration
from .prompt import RESEARCH_INSTRUCTIONS
from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, START, END

from typing import Union
from .agent_schema import (
    ReportState, 
    CommitReportSchema,
    SectionWriterInput,
    ReportOutputState,
    FinishResearch,
)
import httpx
import asyncio
import os
import random
import time
import requests
from urllib.parse import unquote
from bs4 import BeautifulSoup
import concurrent.futures
import aiohttp

@tool(description="Google 검색 API를 사용하여 웹 검색을 수행합니다.")
async def google_search_async(search_queries: Union[str, List[str]], max_results: int = 2, include_raw_content: bool = True):
    """
    Performs concurrent web searches using Google.
    Uses Google Custom Search API if environment variables are set, otherwise falls back to web scraping.

    Args:
        search_queries (List[str]): List of search queries to process
        max_results (int): Maximum number of results to return per query
        include_raw_content (bool): Whether to fetch full page content

    Returns:
        List[dict]: List of search responses from Google, one per query
    """


    # Check for API credentials from environment variables
    api_key = os.environ.get("GOOGLE_API_KEY")
    cx = os.environ.get("GOOGLE_CX")
    use_api = bool(api_key and cx)
    
    # Handle case where search_queries is a single string
    if isinstance(search_queries, str):
        search_queries = [search_queries]
    
    # Define user agent generator
    def get_useragent():
        """Generates a random user agent string."""
        lynx_version = f"Lynx/{random.randint(2, 3)}.{random.randint(8, 9)}.{random.randint(0, 2)}"
        libwww_version = f"libwww-FM/{random.randint(2, 3)}.{random.randint(13, 15)}"
        ssl_mm_version = f"SSL-MM/{random.randint(1, 2)}.{random.randint(3, 5)}"
        openssl_version = f"OpenSSL/{random.randint(1, 3)}.{random.randint(0, 4)}.{random.randint(0, 9)}"
        return f"{lynx_version} {libwww_version} {ssl_mm_version} {openssl_version}"
    
    # Create executor for running synchronous operations
    executor = None if use_api else concurrent.futures.ThreadPoolExecutor(max_workers=5)
    
    # Use a semaphore to limit concurrent requests
    semaphore = asyncio.Semaphore(5 if use_api else 2)
    async def search_single_query(query):
        async with semaphore:
            try:
                results = []
                
                # API-based search
                if use_api:
                    # The API returns up to 10 results per request
                    for start_index in range(1, max_results + 1, 10):
                        # Calculate how many results to request in this batch
                        num = min(10, max_results - (start_index - 1))
                        
                        # Make request to Google Custom Search API
                        params = {
                            'q': query,
                            'key': api_key,
                            'cx': cx,
                            'start': start_index,
                            'num': num
                        }
                        print(f"Requesting {num} results for '{query}' from Google API...")

                        async with aiohttp.ClientSession() as session:
                            async with session.get('https://www.googleapis.com/customsearch/v1', params=params) as response:
                                if response.status != 200:
                                    error_text = await response.text()
                                    print(f"API error: {response.status}, {error_text}")
                                    break
                                    
                                data = await response.json()
                                
                                # Process search results
                                for item in data.get('items', []):
                                    result = {
                                        "title": item.get('title', ''),
                                        "url": item.get('link', ''),
                                        "content": item.get('snippet', ''),
                                        "score": None,
                                        "raw_content": item.get('snippet', '')
                                    }
                                    results.append(result)
                        
                        # Respect API quota with a small delay
                        await asyncio.sleep(0.2)
                        
                        # If we didn't get a full page of results, no need to request more
                        if not data.get('items') or len(data.get('items', [])) < num:
                            break
                
                # Web scraping based search
                else:
                    # Add delay between requests
                    await asyncio.sleep(0.5 + random.random() * 1.5)
                    print(f"Scraping Google for '{query}'...")

                    # Define scraping function
                    def google_search(query, max_results):
                        try:
                            lang = "en"
                            safe = "active"
                            start = 0
                            fetched_results = 0
                            fetched_links = set()
                            search_results = []
                            
                            while fetched_results < max_results:
                                # Send request to Google
                                resp = requests.get(
                                    url="https://www.google.com/search",
                                    headers={
                                        "User-Agent": get_useragent(),
                                        "Accept": "*/*"
                                    },
                                    params={
                                        "q": query,
                                        "num": max_results + 2,
                                        "hl": lang,
                                        "start": start,
                                        "safe": safe,
                                    },
                                    cookies = {
                                        'CONSENT': 'PENDING+987',  # Bypasses the consent page
                                        'SOCS': 'CAESHAgBEhIaAB',
                                    }
                                )
                                resp.raise_for_status()
                                
                                # Parse results
                                soup = BeautifulSoup(resp.text, "html.parser")
                                result_block = soup.find_all("div", class_="ezO2md")
                                new_results = 0
                                
                                for result in result_block:
                                    link_tag = result.find("a", href=True)
                                    title_tag = link_tag.find("span", class_="CVA68e") if link_tag else None
                                    description_tag = result.find("span", class_="FrIlee")
                                    
                                    if link_tag and title_tag and description_tag:
                                        link = unquote(link_tag["href"].split("&")[0].replace("/url?q=", ""))
                                        
                                        if link in fetched_links:
                                            continue
                                        
                                        fetched_links.add(link)
                                        title = title_tag.text
                                        description = description_tag.text
                                        
                                        # Store result in the same format as the API results
                                        search_results.append({
                                            "title": title,
                                            "url": link,
                                            "content": description,
                                            "score": None,
                                            "raw_content": description
                                        })
                                        
                                        fetched_results += 1
                                        new_results += 1
                                        
                                        if fetched_results >= max_results:
                                            break
                                
                                if new_results == 0:
                                    break
                                    
                                start += 10
                                time.sleep(1)  # Delay between pages
                            
                            return search_results
                                
                        except Exception as e:
                            print(f"Error in Google search for '{query}': {str(e)}")
                            return []
                    
                    # Execute search in thread pool
                    loop = asyncio.get_running_loop()
                    search_results = await loop.run_in_executor(
                        executor, 
                        lambda: google_search(query, max_results)
                    )
                    
                    # Process the results
                    results = search_results
                
                # If requested, fetch full page content asynchronously (for both API and web scraping)
                if include_raw_content and results:
                    content_semaphore = asyncio.Semaphore(3)
                    
                    async with aiohttp.ClientSession() as session:
                        fetch_tasks = []
                        
                        async def fetch_full_content(result):
                            async with content_semaphore:
                                url = result['url']
                                headers = {
                                    'User-Agent': get_useragent(),
                                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8'
                                }
                                
                                try:
                                    await asyncio.sleep(0.2 + random.random() * 0.6)
                                    async with session.get(url, headers=headers, timeout=10) as response:
                                        if response.status == 200:
                                            # Check content type to handle binary files
                                            content_type = response.headers.get('Content-Type', '').lower()
                                            
                                            # Handle PDFs and other binary files
                                            if 'application/pdf' in content_type or 'application/octet-stream' in content_type:
                                                # For PDFs, indicate that content is binary and not parsed
                                                result['raw_content'] = f"[Binary content: {content_type}. Content extraction not supported for this file type.]"
                                            else:
                                                try:
                                                    # Try to decode as UTF-8 with replacements for non-UTF8 characters
                                                    html = await response.text(errors='replace')
                                                    soup = BeautifulSoup(html, 'html.parser')
                                                    result['raw_content'] = soup.get_text()
                                                except UnicodeDecodeError as ude:
                                                    # Fallback if we still have decoding issues
                                                    result['raw_content'] = f"[Could not decode content: {str(ude)}]"
                                except Exception as e:
                                    print(f"Warning: Failed to fetch content for {url}: {str(e)}")
                                    result['raw_content'] = f"[Error fetching content: {str(e)}]"
                                return result
                        
                        for result in results:
                            fetch_tasks.append(fetch_full_content(result))
                        
                        updated_results = await asyncio.gather(*fetch_tasks)
                        results = updated_results
                        print(f"Fetched full content for {len(results)} results")
                
                return {
                    "query": query,
                    "follow_up_questions": None,
                    "answer": None,
                    "images": [],
                    "results": results
                }
            except Exception as e:
                print(f"Error in Google search for query '{query}': {str(e)}")
                return {
                    "query": query,
                    "follow_up_questions": None,
                    "answer": None,
                    "images": [],
                    "results": []
                }

    try:
        # Create tasks for all search queries
        search_tasks = [search_single_query(query) for query in search_queries]
        
        # Execute all searches concurrently
        search_results = await asyncio.gather(*search_tasks)
        
        return search_results
    finally:
        # Only shut down executor if it was created
        if executor:
            executor.shutdown(wait=False)


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
    max_results: Annotated[int, InjectedToolArg] = 2,
    topic: Annotated[Literal["general", "news", "finance"], InjectedToolArg] = "general",
    config: RunnableConfig = None
):
    """
    Tavily 검색 API에서 결과를 가져옵니다.
    """
    # try:
    search_results = await tavily_search_async(
        search_queries=queries,
        max_results=max_results,
        topic=topic,
        include_raw_content=True
    )
    # Format the search results directly using the raw_content already provided
    formatted_output = "검색 결과:\n\n"
    source_str = ""
    
    unique_results = {}
    for response in search_results:
        for result in response['results']:
            url = result['url']
            if url not in unique_results:
                unique_results[url] = {**result, "query": response['query']}

    for url, result in unique_results.items():
        formatted_output += f"- **{result['title']}**\n  {url}\n  {result['content'][:1000]}...\n\n"
        source_str += f"- **[{result['title']}]**({url})\n"

    return formatted_output

    # except httpx.HTTPStatusError as e:
    #     return f"[ERROR] Tavily API 호출 실패: {e.response.status_code} - {e.response.text}"
    # except Exception as e:
    #     return f"[ERROR] Tavily API 호출 중 알 수 없는 오류 발생: {str(e)}"




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
    elif search_api.lower() == "googlesearch":
        search_tool = google_search_async
    elif search_api.lower() == "duckduckgo":
        # search_tool = duckduckgo_search_async
        pass
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
    search_str = ""
    
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


        
        # Store the section observation if a Section tool was called
        if tool_call["name"] == "CommitReportSchema":
            completed_section = cast(CommitReportSchema, observation)


        # Store the source string if a search tool was called
        if tool_call["name"] in search_tool_names and configurable.include_source_str:
            if isinstance(observation, list):
                # print("observation:", observation)
                # List of responses
                for response in observation:
                    query = response.get("query", "")
                    for data in response.get("results", []):
                        source_str += (f"- [{data.get('title', '')}]({data.get('url', '')})\n\n")
                        search_str += (f"[{data.get('title', '')}]\n\n({data.get('raw_content', '')[:1000]}...)\n\n")
            elif isinstance(observation, str):
                source_str += cast(str, observation)
        
                # Append to messages 
        result.append({"role": "tool", 
                       "content": search_str, 
                       "name": tool_call["name"], 
                       "tool_call_id": tool_call["id"]})
    
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