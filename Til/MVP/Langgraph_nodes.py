import json
import torch
import uuid
from Prompts import *
from state_types import *
from model import get_til_model
from qdrant_client import QdrantClient
from qdrant_client.models import PointStruct
from langsmith import traceable
from langgraph.graph import StateGraph
import logging

logger = logging.getLogger(__name__)

class Langgraph:
    def __init__(self):
        """Langgraph 초기화"""
        self.prompts = LanggraphPrompts()
        self.model = get_til_model()
        self.client = QdrantClient(host="35.188.172.167", port=6333)
        self.graph = self._build_graph()

    def _build_graph(self) -> StateGraph:
        """StateGraph 구성"""
        builder = StateGraph(StateType)
        builder.set_entry_point("fork")
        builder.add_node("fork", self.fork_code_nodes)

        for i in range(5):
            builder.add_node(f"code_summary_node{i+1}", self.make_code_summary_node(i+1))
            builder.add_node(f"patch_summary_node{i+1}", self.make_patch_summary_node(i+1))
            builder.add_edge("fork", f"code_summary_node{i+1}")
            builder.add_edge(f"code_summary_node{i+1}", f"patch_summary_node{i+1}")

        builder.add_node("til_draft_node", self.til_draft_node)
        for i in range(5):
            builder.add_edge(f"patch_summary_node{i+1}", "til_draft_node")

        builder.add_node("json_parse_node", self.parse_til_to_json)
        builder.add_edge("til_draft_node", "json_parse_node")

        builder.add_node("embedding_til_node", self.embed_and_store_in_qdrant_node)
        builder.add_edge("json_parse_node", "embedding_til_node")

        builder.set_finish_point("embedding_til_node")
        return builder.compile()

    @traceable
    def fork_code_nodes(self, state: dict) -> dict:
        """파일별 노드 분기"""
        files = state.get("files", [])
        updated_files = [
            {
                "file": file,
                "node_id": i + 1
            }
            for i, file in enumerate(files)
        ]
        state["files"] = updated_files
        return state

    def make_code_summary_node(self, node_id: int):
        """코드 요약 노드 생성"""
        @traceable(run_type="llm")
        async def code_summary_node(state: dict):
            files = state["files"]
            file_entry = next(file for file in files if file["node_id"] == node_id)
            file = file_entry["file"]

            prompt = self.prompts.make_code_summary_prompt(file)
            summary = await self.model.generate_til(prompt)

            return {"code_summary": {f"code_summary_{node_id}": summary}}
        return code_summary_node

    def make_patch_summary_node(self, node_id: int):
        """패치 요약 노드 생성"""
        @traceable(run_type="llm")
        async def patch_summary_node(state: dict):
            files = state["files"]
            file_entry = next(file for file in files if file["node_id"] == node_id)
            file = file_entry["file"]

            code_summaries = state.get("code_summary", {})
            code_summary = code_summaries.get(f"code_summary_{node_id}", "")

            patches = file.get("patches", [])
            if not patches:
                return {"patch_summary": {f"patch_summary_{node_id}": f"{code_summary}\n\n(변경 이력 없음)"}}
            
            patch_section = "\n\n".join(
                f"{j+1}. Commit Message: {p['commit_message']}\nPatch:\n{p['patch']}"
                for j, p in enumerate(patches)
            )

            prompt = self.prompts.make_patch_summary_prompt(code_summary, patch_section)
            summary = await self.model.generate_til(prompt)

            return {"patch_summary": {f"patch_summary_{node_id}": summary}}
        return patch_summary_node

    @traceable
    async def til_draft_node(self, state: dict) -> dict:
        """TIL 초안 생성"""
        username = state.get("username", "unknown_user")
        date = state.get("date", "unknown_date")
        repo = state.get("repo", "unknown_repo")

        patch_summaries = state.get("patch_summary", {})
        summaries = list(patch_summaries.values())
        combined_summary = "\n\n".join(summaries)

        prompt = self.prompts.til_draft_prompt(username, date, repo, combined_summary)
        draft_json_str = await self.model.generate_til(prompt)
        return {"til_draft": draft_json_str}

    @traceable
    def parse_til_to_json(self, state: dict) -> dict:
        """TIL 초안을 JSON으로 파싱"""
        til_draft = state.get("til_draft", "")
        try:
            start = til_draft.find("```json")
            end = til_draft.find("```", start + 1)
            json_str = til_draft[start + 7:end].strip()
            parsed = json.loads(json_str)
            return {"til_json": parsed}
        except Exception as e:
            logger.error(f"JSON 파싱 실패: {e}")
            return {"til_json": {"error": f"JSON 파싱 실패: {str(e)}"}}

    @traceable
    async def embed_and_store_in_qdrant_node(self, state: dict) -> dict:
        """TIL 임베딩 생성 및 저장"""
        til_json = state.get("til_json")
        if not til_json:
            raise ValueError("til_json is missing from state")

        title = til_json["title"]
        content = til_json["content"]
        text = f"query: {title}\n{content}"

        try:
            embedding = await self.model.get_embedding(text)
            payload = {k: v for k, v in til_json.items() if k != "vector"}

            point = PointStruct(
                id=str(uuid.uuid4()),
                vector=embedding,
                payload=payload
            )

            self.client.upsert(collection_name="til_logs", points=[point])

            til_json["vector"] = embedding
            return {"til_json": til_json}
            
        except Exception as e:
            logger.error(f"임베딩 생성 또는 저장 실패: {e}")
            raise