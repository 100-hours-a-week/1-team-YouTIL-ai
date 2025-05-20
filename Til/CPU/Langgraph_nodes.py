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
    def __init__(self, num_files, model):
        self.prompts = LanggraphPrompts()
        self.model = model
        # self.client = QdrantClient(host="104.154.17.188", port=6333)
        self.files_num = num_files
        self.graph = self._build_graph()
        

    def _build_graph(self) -> StateGraph:
        builder = StateGraph(StateModel)

        # 1. 시작점
        builder.set_entry_point("fork")
        builder.add_node("fork", self.fork_code_nodes)

        # 2. 병렬 draft 노드들 (최대 5개)
        max_nodes = min(self.files_num, 5)
        for i in range(max_nodes):
            node_name = f"draft_{i}"
            builder.add_node(node_name, self.make_til_draft_node(i))
            builder.add_edge("fork", node_name)

        # 3. 종합 노드: til_final 구성
        builder.add_node("final_til_node", self.generate_final_til_node)
        for i in range(max_nodes):
            builder.add_edge(f"draft_{i}", "final_til_node")

        # 4. 키워드 추출 노드
        builder.add_node("til_keywords_node", self.til_keywords_node)
        builder.add_edge("final_til_node", "til_keywords_node")

        # 5. 종료점
        builder.set_finish_point("til_keywords_node")

        return builder.compile()

    @traceable
    def fork_code_nodes(self, state: StateModel) -> StateModel:
        return state.model_copy(
            update={
                "files": [
                    file.model_copy(update={"node_id": i})
                    for i, file in enumerate(state.files)
                ]
            }
        )
    def make_til_draft_node(self, node_id: int):
        async def til_draft_node(state: StateModel) -> dict:
            files = state.files
            file_entry = next(file for file in files if file.node_id == node_id)
            
            username = state.username
            date = state.date
            repo = state.repo


            patches = file_entry.patches[0]
            latest_code = file_entry.latest_code

            preprocessed = []

            for p in patches:
                commit, patch = p 

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

            file_entry.til_content = draft_json_str.strip()

            return {"status": "ok", "node_id": node_id}
        return til_draft_node

    @traceable
    async def generate_final_til_node(self, state: StateModel) -> dict:
        username = state.username
        date = state.date
        repo = state.repo
        files = state.files

        # til_content가 존재하는 파일만 추출
        file_tils = [(f.filepath, f.til_content.strip()) for f in files if f.til_content.strip()]

        if not file_tils:
            return {
                "til_final": TilJsonModel(
                    username=username,
                    date=date,
                    repo=repo,
                    keywords=[],  # 다음 노드에서 추출
                    content="⚠️ 작성된 TIL 초안이 없습니다."
                )
            }

        # 파일별 section 구성
        sections = []
        for filepath, content in file_tils:
            section = f"## `{filepath}`\n\n{content}\n"
            sections.append(section)

        # 전체 TIL 본문 구성
        combined_content = f"# {date} TIL by {username}\n\n" + "\n".join(sections)
        prompt = self.prompts.make_final_til_prompt(date, combined_content)
        final_til = await self.model.generate(prompt, 4096)

        til_json = TilJsonModel(
            username=username,
            date=date,
            repo=repo,
            keywords=[],  # 다음 노드에서 추출
            content=final_til
        )

        return {"til_final": til_json}

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