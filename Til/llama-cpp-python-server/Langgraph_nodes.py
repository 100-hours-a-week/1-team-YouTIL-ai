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

def clean_keywords_output(keywords: str) -> str:
    lines = keywords.strip().split('\n')

    keywords = []
    for line in lines:
        # 1. 숫자. 제거 (줄 맨 앞에 있는 "숫자. " 패턴만 제거)
        line = re.sub(r'^\s*\d+\.\s*', '', line)

        # 2. 좌우 공백 + 불필요한 기호 제거: -, ", '
        line = line.strip().lstrip('-').strip().strip('"').strip("'").strip()

        # 3. 괄호 처리: "함수 (설명)" → "함수", "설명"
        match = re.match(r'(.+?)\s*\((.+?)\)', line)
        if match:
            main, extra = match.groups()
            keywords.append(main.strip())
            keywords.append(extra.strip())
        else:
            keywords.append(line)
    return keywords

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
        self.files_num = num_files
        self.graph = self._build_graph()
        

    def _build_graph(self) -> StateGraph:
        builder = StateGraph(StateModel)

        # 1. 시작점
        builder.set_entry_point("fork")
        builder.add_node("fork", self.fork_code_nodes)

        max_nodes = min(self.files_num, 5)
        for i in range(max_nodes):
            node_name = f"draft_{i}"
            builder.add_node(node_name, self.make_til_draft_node(i))
            builder.add_edge("fork", node_name)

        builder.add_node("final_til_node", self.generate_final_til_node)
        for i in range(max_nodes):
            builder.add_edge(f"draft_{i}", "final_til_node")

        builder.add_node("translate_til_node", self.translate_til_node)
        builder.add_edge("final_til_node", "translate_til_node")

        # 4. 키워드 추출 노드
        builder.add_node("til_keywords_node", self.til_keywords_node)
        builder.add_edge("translate_til_node", "til_keywords_node")

        # 5. 종료점
        builder.set_finish_point("til_keywords_node")

        return builder.compile()

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
        @traceable(run_type='llm')
        async def til_draft_node(state: StateModel) -> dict:
            files = state.files
            file_entry = next(file for file in files if file.node_id == node_id)
            
            date = state.date

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

            prompt = self.prompts.make_til_draft(final)
            draft_json_str = await self.model.generate(prompt, 
                                                    max_tokens=2024,
                                                    temperature=0.6,
                                                    top_p=0.9,
                                                    frequency_penalty=0.3,
                                                    repeat_penalty=1.1,
                                                    stop=[]
                                                    )


            file_entry.til_content = draft_json_str.strip()

            return {
            "til_content": file_entry.til_content
            }
        return til_draft_node

    @traceable(run_type='llm')
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
        final_til = await self.model.generate(prompt, 
                                                    max_tokens=4096,
                                                    temperature=0.3,
                                                    top_p=0.9,
                                                    frequency_penalty=0.3,
                                                    repeat_penalty=1.1,
                                                    stop=[]
                                                    )

        til_json = TilJsonModel(
            username=username,
            date=date,
            repo=repo,
            keywords=[],  # 다음 노드에서 추출
            content=final_til,
            vector=[]
        )

        return {"til_json": til_json}

    @traceable(run_type='llm')
    async def translate_til_node(self, state: StateModel) -> dict:
        date = state.date
        content = state.til_json.content

        prompt = self.prompts.til_translate_prompt(date, content)
        final_til = await self.model.translate(prompt, 
                                            max_tokens=2400,
                                            temperature=0.3,
                                            top_p=0.9,
                                            frequency_penalty=0.3,
                                            repeat_penalty=1.1,
                                            stop=["**지시사항**"]
                                            )
        state.til_json.content = final_til

        return {"til_json": state.til_json}


    async def til_keywords_node(self, state: StateModel) -> dict:
        content = state.til_json.content
        prompt = LanggraphPrompts.til_keywords_prompt(content)
        
        max_attempts = 3
        for attempt in range(1, max_attempts + 1):
            keywords_output = await self.model.generate(prompt, 
                                                    max_tokens=64,
                                                    temperature=0.3,
                                                    top_p=0.9,
                                                    frequency_penalty=0.3,
                                                    repeat_penalty=1.1,
                                                    stop=[]
                                                    )
            
            keywords_output = clean_llm_output(keywords_output)

            try:
                # case 1: 이미 list인 경우
                if isinstance(keywords_output, list):
                    parsed = keywords_output
                # case 2: 문자열인 경우
                elif isinstance(keywords_output, str):
                    parsed = ast.literal_eval(keywords_output)
                else:
                    raise ValueError(f"지원하지 않는 타입: {type(keywords_output)}")

                # 리스트 유효성 검사
                if isinstance(parsed, list) and all(isinstance(k, str) for k in parsed):
                    state.til_json.keywords = parsed[:3]
                    break
                else:
                    raise ValueError("리스트 안에 문자열이 아닌 값이 있음")

            except Exception as e:
                logging.warning(f"[til_keywords_node] 키워드 파싱 실패 (시도 {attempt}/{max_attempts}): {e}")
                if attempt == max_attempts:
                    logging.error("[til_keywords_node] 키워드 파싱 3회 실패, 원본 문자열 저장")
                    state.til_json.keywords = str(keywords_output).strip()

        return {"til_json": state.til_json}