import json
import uuid
from Prompts import *
from state_types import *
from model import *
from qdrant_client import QdrantClient
from qdrant_client.models import PointStruct
from langsmith import traceable
from langgraph.graph import StateGraph
import logging

logger = logging.getLogger(__name__)

class Langgraph:
    def __init__(self, files_num, model: TILModels):
        self.prompts = LanggraphPrompts()
        self.model = model
        self.client = QdrantClient(host="34.29.126.77", port=6333)
        self.files_num = files_num
        self.graph = self._build_graph()
        

    def _build_graph(self) -> StateGraph:
        builder = StateGraph(StateModel)
        builder.set_entry_point("fork")
        builder.add_node("fork", self.fork_code_nodes)
        # 동적 node 수 결정 (최대 5개)
        max_nodes = min(self.files_num, 5)


        for i in range(max_nodes):
            builder.add_node(f"code_summary_node{i+1}", self.make_code_summary_node(i+1))
            builder.add_node(f"patch_summary_node{i+1}", self.make_patch_summary_node(i+1))
            builder.add_edge("fork", f"code_summary_node{i+1}")
            builder.add_edge(f"code_summary_node{i+1}", f"patch_summary_node{i+1}")

        builder.add_node("til_draft_node", self.til_draft_node)
        for i in range(max_nodes):
            builder.add_edge(f"patch_summary_node{i+1}", "til_draft_node")

        builder.add_node("json_parse_node", self.parse_til_to_json)
        builder.add_edge("til_draft_node", "json_parse_node")

        builder.add_node("embedding_til_node", self.embed_and_store_in_qdrant_node)
        builder.add_edge("json_parse_node", "embedding_til_node")

        builder.set_finish_point("embedding_til_node")
        return builder.compile()

    @traceable
    def fork_code_nodes(self, state: StateModel) -> StateModel:
        return state.model_copy(
            update={
                "files": [
                    file.model_copy(update={"node_id": i + 1})
                    for i, file in enumerate(state.files)
                ]
            }
        )

    def make_code_summary_node(self, node_id: int):
        @traceable(run_type="llm")
        async def code_summary_node(state: StateModel) -> dict:
            file = next(file for file in state.files if file.node_id == node_id)

            prompt = self.prompts.make_code_summary_prompt(file)
            summary = await self.model.generate_til(prompt)

            return {"code_summary": {f"code_summary_{node_id}": summary}}
        return code_summary_node

    def make_patch_summary_node(self, node_id: int):
        @traceable(run_type="llm")
        async def patch_summary_node(state: StateModel) -> dict:
            files = state.files
            file_entry = next(file for file in files if file.node_id == node_id)


            code_summaries = state.code_summary
            code_summary = code_summaries.get(f"code_summary_{node_id}", "")
            patches = file_entry.patches
            if not patches:
                return {"patch_summary": {f"patch_summary_{node_id}": f"{code_summary}\n\n(변경 이력 없음)"}}

            patch_section = "\n\n".join(
                f"{j+1}. Commit Message: {p.commit_message}\nPatch:\n{p.patch}"
                for j, p in enumerate(patches)
            )
            prompt = self.prompts.make_patch_summary_prompt(code_summary, patch_section)
            summary = await self.model.generate_til(prompt)

            return {"patch_summary": {f"patch_summary_{node_id}": summary}}
        return patch_summary_node

    @traceable
    async def til_draft_node(self, state: StateModel) -> dict:
        username = state.username
        date = state.date
        repo = state.repo

        patch_summaries = state.patch_summary
        summaries = list(patch_summaries.values())
        combined_summary = "\n\n".join(summaries)
        prompt = self.prompts.til_draft_prompt(username, date, repo, combined_summary)
        draft_json_str = await self.model.generate_til(prompt)
        return {"til_draft": draft_json_str}

    @traceable
    async def parse_til_to_json(self, state: StateModel) -> dict:
        til_draft = state.til_draft
        try:
            start =til_draft.find("```json")
            end = til_draft.find("```", start + 1)
            json_str = til_draft[start + 7:end].strip()
            parsed = json.loads(json_str)
            return {"til_json": parsed}
        except Exception as e:
            logger.error(f"JSON 파싱 실패: {e}")
            return {"til_json": {"error": f"JSON 파싱 실패: {str(e)}"}}

    @traceable
    async def embed_and_store_in_qdrant_node(self, state: StateModel) -> dict:
        til_json = state.til_json
        if not til_json:
            raise ValueError("til_json is missing from state")

        title = til_json.title
        content = til_json.content
        text = f"query: {title}\n{content}"

        try:
            embedding = await self.model.get_embedding(text)
            payload = {k: v for k, v in til_json.model_dump().items() if k != "vector"}

            point = PointStruct(
                id=str(uuid.uuid4()),
                vector=embedding,
                payload=payload
            )

            self.client.upsert(collection_name="til_logs", points=[point])
            til_json.vector = embedding
            return state.til_json

        except Exception as e:
            logger.error(f"임베딩 생성 또는 저장 실패: {e}")
            raise
