import os
import uuid
from app.prompts.Prompts import LanggraphPrompts
from app.schemas.state_types import TilJsonModel, StateModel, PatchSummaryModel, TILKeywordsModel
from app.models.model import TILModel
from app.models.embedding import EmbeddingModel
from qdrant_client import QdrantClient
from qdrant_client.models import PointStruct
from langsmith import traceable
from langgraph.graph import StateGraph
from pydantic import ValidationError
import logging
import ast

logger = logging.getLogger(__name__)

# 커밋 이력 데이터 
def extract_before_after(diff_lines):
    before_lines = []
    after_lines = []
    for line in diff_lines:
        if line.startswith('-') and not line.startswith('---'):
            before_lines.append(line[1:].strip())
        elif line.startswith('+') and not line.startswith('+++'):
            after_lines.append(line[1:].strip())
    return before_lines, after_lines


class Langgraph:
    def __init__(self, files_num, model: TILModel, embedding: EmbeddingModel):
        self.prompts = LanggraphPrompts()
        self.model = model
        self.embedding = embedding
        self.client = QdrantClient(host=os.getenv("DB_SERVER_IP"), port=6333)
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
        builder.add_node("til_keywords_node", self.til_keywords_node)
        builder.add_edge("til_draft_node", "til_keywords_node")
        builder.add_node("embedding_til_node", self.embed_and_store_in_qdrant_node)
        builder.add_edge("til_keywords_node", "embedding_til_node")
        builder.set_finish_point("embedding_til_node")
        return builder.compile()

    @traceable(
            name="fork_commit_node",
            run_type="tool",
            tags=["fork_node"],
            metadata={"component":"fork_commit","version":"v2",} 
               )
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
        @traceable(
            name="generate_code_summary_node",
            run_type="llm",
            tags=["code"],
            metadata={"component":"code_summary","version":"v2",} 
               )
        async def code_summary_node(state: StateModel) -> dict:
            params = {
                "temperature": 0.3,
                "top_p": 0.95,
                "max_tokens": 1024,
                "repetition_penalty": 1.1,
                "stop": ["<eos>", "<pad>", "```", "<```>"],
                "stop_token_ids": [12234, 2, 7243, 2717]
            }

            file = next(file for file in state.files if file.node_id == node_id)

            prompt = self.prompts.make_code_summary_prompt(file)
            summary = await self.model.generate(prompt, params)

            return {"code_summary": {f"code_summary_{node_id}": summary}}
        return code_summary_node

    def make_patch_summary_node(self, node_id: int):
        @traceable(
            name="generate_patches_summary_node",
            run_type="llm",
            tags=["patches"],
            metadata={"component":"patches_summary","version":"v2",} 
               )
        async def patch_summary_node(state: StateModel) -> dict:
            params = {
                "temperature": 0.3,
                "top_p": 0.95,
                "max_tokens": 512,
                "repetition_penalty": 1.1,
                "stop": ["<eos>", "<pad>", "```", "<```>"],
                "stop_token_ids": [12234, 2, 7243, 2717]
            }

            files = state.files
            file_entry = next(file for file in files if file.node_id == node_id)
            
            patches = file_entry.patches
            preprocessed = []

            for p in patches:
                commit = p.commit_message
                patch = p.patch

                preprocessed.append({
                    "commit_message": commit,
                    "raw_patch": patch,
                    "diff_lines": patch.splitlines()
                })

            final = []
            for p in preprocessed:
                before, after = extract_before_after(p["diff_lines"])
                final.append({
                    "commit_message": p["commit_message"],
                    "before_code": "\n".join(before),
                    "after_code": "\n".join(after)
                })

             # 최신 변경 내역 사용
            latest_patch = final[0] 

            code_summaries = state.code_summary
            code_summary = code_summaries.get(f"code_summary_{node_id}", "")

            prompt = self.prompts.make_patch_summary_prompt(code_summary, latest_patch["commit_message"], latest_patch["before_code"], latest_patch["after_code"])
            summary = await self.model.generate(prompt, params)

            return {"patch_summary": 
                    [PatchSummaryModel(
                        filepath=file_entry.filepath,
                        change_purpose=patches[0].commit_message,  # 최신 커밋
                        code_changes=summary)]}

        return patch_summary_node

    @traceable(
            name="generate_til_node",
            run_type="llm",
            tags=["til"],
            metadata={"component":"generate_til","version":"v2",} 
               )
    async def til_draft_node(self, state: StateModel) -> dict:


        params = {
            "temperature": 0.3,
            "top_p": 0.95,
            "max_tokens": 2024,
            "repetition_penalty": 1.1,
            "stop": ["<eos>", "<pad>", "```", "<```>"],
            "stop_token_ids": [12234, 2, 7243, 2717]
        }
        username = state.username
        date = state.date
        repo = state.repo
        patch_summaries = state.patch_summary
        prompt = self.prompts.til_draft_prompt(username, date, repo, patch_summaries)
        draft_json_str = await self.model.generate(prompt, params)
        # Til 끝에 ''' 제거
        draft_json_str = draft_json_str.replace("```", "").replace("'''", "")

        parsed = TilJsonModel(
        username=username,
        date=date,
        repo=repo,
        keywords=TILKeywordsModel(keywords_list=[]),
        content=draft_json_str,
        vector=[])

        return {"til_json": parsed}
        
    @traceable(
            name="keywords_from_til_node",
            run_type="llm",
            tags=["keywords"],
            metadata={"component":"keyowrds_from_til","version":"v2",} 
               )
    async def til_keywords_node(self, state: StateModel) -> dict:
        json_schema = TILKeywordsModel.model_json_schema()
        extra_body={"guided_json": json_schema}
        params = {
            "temperature": 0.3,
            "top_p": 0.95,
            "max_tokens": 256,
            "repetition_penalty": 1.1,
            "stop": ["<eos>", "<pad>", "```", "<```>"],
            "stop_token_ids": [12234, 2, 7243, 2717],
        }

        content = state.til_json.content
        prompt = LanggraphPrompts.til_keywords_prompt(content)

        max_attempts = 3
        for attempt in range(1, max_attempts + 1):
            try:
                keywords_output = await self.model.generate(prompt, params, extra_body)
                print("[🧪 Raw output]", keywords_output)

                # pydantic 기반 파싱 시도
                parsed = TILKeywordsModel.parse_raw(keywords_output)

                # 최대 3개까지만 반영
                trimmed_keywords = parsed.keywords_list[:3]
                state.til_json.keywords = TILKeywordsModel(keywords_list=trimmed_keywords)
                break

            except ValidationError as e:
                logging.warning(f"[til_keywords_node] JSON 파싱 실패 (시도 {attempt}/{max_attempts}): {e}")
                if attempt == max_attempts:
                    logging.error("[til_keywords_node] 키워드 파싱 3회 실패, 원본 문자열 저장")
                    state.til_json.keywords = TILKeywordsModel(keywords_list=[keywords_output.strip()])

    @traceable
    async def embed_and_store_in_qdrant_node(self, state: StateModel) -> dict:
        til_json = state.til_json
        if not til_json:
            raise ValueError("til_json is missing from state")

        content = til_json.content
        text = f"query: {content}"

        try:
            embedding = await self.embedding.get_embedding(text)
            payload = {k: v for k, v in til_json.model_dump().items() if k != "vector"}

            point = PointStruct(
                id=str(uuid.uuid4()),
                vector=embedding,
                payload=payload
            )

            self.client.upsert(collection_name="til_logs", points=[point])
            til_json.vector = embedding
            return {"til_json": state.til_json}

        except Exception as e:
            logger.error(f"임베딩 생성 또는 저장 실패: {e}")
            raise
