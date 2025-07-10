from langsmith import traceable
from langchain.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langgraph.graph import StateGraph, START, END
from langchain_openai import ChatOpenAI
from langchain.chat_models import init_chat_model
from .agent_schema import (
    CommitDataSchema,
    CommitAnalysisSchema,
    TilState
)
from langchain_core.runnables import RunnableConfig
from .config import MultiAgentConfiguration
from .prompt import COMMIT_REVIEW_INSTRUCTIONS
from .utils import get_config_value
import os


class CommitAnalysisGraph:
    def __init__(self, no_files: int):
        self.no_files = no_files

    @staticmethod
    @traceable(run_type="tool")
    async def fork_files_nodes(state: CommitDataSchema) -> dict:
        files = state.files
        for idx, file in enumerate(files):
            file.node_id = idx + 1
        return {
            "files": files,
            "date": state.date,
        }

    ## code analysis nodes
    @staticmethod
    def make_code_summary_node(node_id: int):
        @traceable(
                run_type="chain", 
                name=f"summarize_code_{node_id}"
                )
        async def summarize_code(state:CommitDataSchema, config: RunnableConfig) -> CommitDataSchema:
            configurable = MultiAgentConfiguration.from_runnable_config(config)
            model = get_config_value(configurable.code_analysis_model)
            llm = init_chat_model(model)
            files = state.files
            system_prompt = COMMIT_REVIEW_INSTRUCTIONS
            user_prompt = """[file name]: {file_name}
    --------------------------------
    [code]: {code}
    --------------------------------
    [patches]: {patches}"""
            
            target_file = None
            for file in files:
                if file.node_id == node_id:
                    target_file = file
                    break
            file_name = target_file.filepath
            code = target_file.latest_code
            patches = target_file.patches

            for i, patch in enumerate(patches):
                patches_str = f"[commit message {i+1}]: " + patch.commit_message + "\n"
                patches_str += "[code diff]: \n"
                patches_str += patch.patch + "\n"
                patches_str += "--------------------------------"

            code_analysis_prompt = ChatPromptTemplate.from_messages(
                [
                    ("system", system_prompt),
                    ("user", user_prompt),
                ]
            )

            code_analysis_chain = (
                code_analysis_prompt 
                | llm 
                | StrOutputParser()
            )
            
            result: CommitAnalysisSchema = await code_analysis_chain.ainvoke(
                {
                    "file_name": file_name, 
                    "code": code, 
                    "patches": patches_str
                }
            )
            
            result_dict = {
                "filename": file_name,
                "code_review": result,
                "code": code,
                "code_diff": patches
            }

            commit_analysis_result = CommitAnalysisSchema(**result_dict)
            return {'sections': [commit_analysis_result]}
        
        return summarize_code

    def make_commit_analysis_graph(self):
        commit_analysis_graph = StateGraph(CommitDataSchema, output=TilState)

        # node
        commit_analysis_graph.add_node("fork_files_nodes", self.fork_files_nodes)
        commit_analysis_graph.add_edge(START, "fork_files_nodes")

        for i in range(self.no_files):
            node_id = i+1
            file_summary_node = self.make_code_summary_node(node_id)
            commit_analysis_graph.add_node(f"summarize_file_node_{node_id}", file_summary_node)
            commit_analysis_graph.add_edge("fork_files_nodes", f"summarize_file_node_{node_id}")
            commit_analysis_graph.add_edge(f"summarize_file_node_{node_id}", END)
        
        commit_analysis_graph = commit_analysis_graph.compile()

        return commit_analysis_graph