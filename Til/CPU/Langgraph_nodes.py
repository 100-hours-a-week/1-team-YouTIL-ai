import re
import logging
import ast

from model import LLM
from Prompts import LanggraphPrompts
from state_types import StateModel, TilJsonModel
from langsmith import traceable
from langgraph.graph import StateGraph



def extract_before_after(diff_lines):
    before_lines = []
    after_lines = []
    for line in diff_lines:
        if line.startswith('-') and not line.startswith('---'):
            before_lines.append(line[1:].strip())
        elif line.startswith('+') and not line.startswith('+++'):
            after_lines.append(line[1:].strip())
    return before_lines, after_lines

def extract_before_after(diff_lines):
    before_lines = []
    after_lines = []
    for line in diff_lines:
        if line.startswith('-') and not line.startswith('---'):
            before_lines.append(line[1:].strip())
        elif line.startswith('+') and not line.startswith('+++'):
            after_lines.append(line[1:].strip())
    return before_lines, after_lines

# 특수 문제 전처리 함수(제목, 키워드)
def clean_llm_output(output: str) -> str:
    # 코드 블록 제거 (```로 감싼 블록)
    output = re.sub(r"```.*?```", "", output, flags=re.DOTALL)
    # 코드 블록 시작/종료 따로도 제거 (단독 줄 또는 끝에 오는 것 포함)
    output = re.sub(r"```", "", output)
    # 마크다운 구분선/헤더 제거
    output = re.sub(r"^---+", "", output, flags=re.MULTILINE)
    output = re.sub(r"^#+ .*", "", output, flags=re.MULTILINE)
    output = output.replace("```", "").replace("'''", "")
    # "답변:", "제목:" 등 앞 단어 제거
    output = re.sub(r"(?i)^.*?[:：]", "", output, count=1)
    # 슬래시(/) 제거 또는 대체
    output = output.replace("/", " ")  # 또는 .replace("/", "") if 공백도 싫다면
    output = output.replace("\\", " ")  # 또는 .replace("/", "") if 공백도 싫다면
    # 줄바꿈 → 공백
    output = output.replace("\n", " ")
    return output.strip()

class Langgraph:
    def __init__(self, model):
        self.prompts = LanggraphPrompts()
        self.model = model
        # self.model = model
        # self.client = QdrantClient(host="104.154.17.188", port=6333)
        # self.files_num = files_num
        self.graph = self._build_graph()
        

    def _build_graph(self) -> StateGraph:
        builder = StateGraph(StateModel)
        builder.set_entry_point("til_draft_node")
        builder.add_node("til_draft_node", self.til_draft_node)
        builder.add_node("til_keywords_node", self.til_keywords_node)
        builder.add_edge("til_draft_node", "til_keywords_node")
        builder.set_finish_point("til_keywords_node")
        
        # builder.set_entry_point("fork")
        # builder.add_node("fork", self.fork_code_nodes)
        # 동적 node 수 결정 (최대 5개)
        # max_nodes = min(self.files_num, 5)


        # for i in range(max_nodes):
        #     builder.add_node(f"code_summary_node{i+1}", self.make_code_summary_node(i+1))
        #     builder.add_node(f"patch_summary_node{i+1}", self.make_patch_summary_node(i+1))
        #     builder.add_edge("fork", f"code_summary_node{i+1}")
        #     builder.add_edge(f"code_summary_node{i+1}", f"patch_summary_node{i+1}")
        # builder.add_node("til_draft_node", self.til_draft_node)
        # for i in range(max_nodes):
        #     builder.add_edge(f"patch_summary_node{i+1}", "til_draft_node")
        # builder.add_node("til_keywords_node", self.til_keywords_node)
        # builder.add_edge("til_draft_node", "til_keywords_node")
        # builder.add_node("embedding_til_node", self.embed_and_store_in_qdrant_node)
        # builder.add_edge("til_keywords_node", "embedding_til_node")
        # builder.set_finish_point("embedding_til_node")

        return builder.compile()

    async def til_draft_node(self, state: StateModel) -> dict:
        username = state.username
        date = state.date
        repo = state.repo


        patches = state.files[0].patches
        latest_code = state.files[0].latest_code

        preprocessed = []

        for p in patches:
            commit = p.commit_message
            patch = p.patch

            preprocessed.append({
                "commit_message": commit,
                "raw_patch": patch,
                "diff_lines": patch.splitlines()
            })

        final = {"latest_code":latest_code,
                "code_changes":[]}
        for p in preprocessed:
            before, after = extract_before_after(p["diff_lines"])
            final["code_changes"].append({
                "commit_message": p["commit_message"],
                "before_code": "\n".join(before),
                "after_code": "\n".join(after)
            })

        prompt = self.prompts.make_til_draft(date, final)
        draft_json_str = await self.model.generate(prompt, 2048)

        parsed = TilJsonModel(
        username=username,
        date=date,
        repo=repo,
        keywords="",
        content=draft_json_str,
        vector=[])

        return {"til_json": parsed}

    async def til_keywords_node(self, state: StateModel) -> dict:

        content = state.til_json.content
        prompt = LanggraphPrompts.til_keywords_prompt(content)

        max_attempts = 3
        for attempt in range(1, max_attempts + 1):
            keywords_output = await self.model.generate(prompt, 64)
            keywords_output = clean_llm_output(keywords_output)

            try:
                parsed = ast.literal_eval(keywords_output)
                if isinstance(parsed, list) and all(isinstance(k, str) for k in parsed):
                    state.til_json.keywords = parsed[:3]
                    break  # 파싱 성공
                else:
                    raise ValueError("응답이 리스트 형식이 아님")
            except Exception as e:
                logging.warning(f"[til_keywords_node] 키워드 파싱 실패 (시도 {attempt}/{max_attempts}): {e}")
                if attempt == max_attempts:
                    logging.error("[til_keywords_node] 키워드 파싱 3회 실패, 원본 문자열 저장")
                    state.til_json.keywords = keywords_output.strip()

        return {"til_json": state.til_json}