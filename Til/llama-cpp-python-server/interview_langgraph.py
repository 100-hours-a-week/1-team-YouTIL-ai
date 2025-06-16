from tenacity import retry, stop_after_attempt, wait_fixed
from langgraph.graph import StateGraph
from langsmith import traceable
from interview_schemas import QAState, ContentState
from model import LLM
import asyncio
import logging
import re

logger = logging.getLogger(__name__)

class QAFlow:
    def __init__(self, llm, templates):
        self.llm = llm
        self.templates = templates
    
    def sync_generate_completion(self, prompt: str, max_tokens: int, temperature: float, stop: list[str] = None) -> str:
        def sync_call():
            return self.llm.model.create_completion(
                prompt=prompt.strip(),
                max_tokens=max_tokens,
                temperature=temperature,
                top_p=0.95,
                frequency_penalty=0.3,
                repeat_penalty=1.1,
                stop=stop or []
            )["choices"][0]["text"].strip()

        return asyncio.get_event_loop().run_in_executor(None, sync_call)

    def clean_korean_question(self, text: str) -> str:

        text = re.sub(r'\*\*(.*?)\*\*', r'\1', text)

        text = re.sub(r'\*\*?(Question|Answer|Note|Level).*?\*\*?', '', text, flags=re.IGNORECASE)
        text = re.sub(r'(Question|Answer|Level)\s*[:：]*', '', text, flags=re.IGNORECASE)
        text = re.sub(r'^#+\s*', '', text)

        text = re.sub(r'^[-•\s]+\d*\s*', '', text)

        text = text.replace("`", "").replace("“", "").replace("”", "")
        text = text.replace("👉", "").replace("→", "").strip()
        text = text.strip().strip('"“”')

        lines = [line.strip() for line in text.split('\n') if line.strip()]

        return lines[0] if lines else ""

    def sanitize_prompt(self, prompt: str) -> str:
        if prompt.startswith("<s>"):
            prompt = prompt[len("<s>"):].lstrip()
        return prompt

    def generate_question_node(self, node_id: int):
        @traceable(name=f"질문 생성 노드 {node_id}", run_type="llm")
        async def question_node(state: QAState) -> dict:
            prompt1 = getattr(self.templates, f"question{node_id}_prompt").format(
                til=state.til,
                level=state.level,
            )
            prompt1 = self.sanitize_prompt(prompt1)

            try:
                final_text = await asyncio.wait_for(
                    self.llm.question_generate(prompt1),
                    timeout=20
                )

                cleaned_question = self.clean_korean_question(final_text)
                return {f"question{node_id}": cleaned_question}
            
            except asyncio.TimeoutError:
                logger.error(f"❗질문 생성 {node_id} 타임아웃")
                return {f"question{node_id}": "[질문 생성 실패]"}
            
            except Exception as e:
                logger.error(f"질문 생성 실패: {e}")
                return {f"question{node_id}": ""}

        return question_node

    def delete_blank(self, text: str) -> str:
        text = re.sub(r"(?<!\n)\n(###)", r"\n\n\1", text)

        lines = text.splitlines()
        cleaned_lines = [
            line if line.startswith("###") or line.strip() == "" else line.lstrip()
            for line in lines
        ]

        return "\n".join(cleaned_lines)

    def generate_answer_node(self, node_id: int):
        @traceable(name=f"답변 생성 노드 {node_id}", run_type="llm")
        async def answer_node(state: QAState) -> dict:
            question = getattr(state, f"question{node_id}", "")
            if not question:
                    logger.warning(f"⚠️ 질문 {node_id}가 비어 있음 → fallback 처리")
                    return {
                        f"content{node_id}": ContentState(
                            question="[질문 없음]",
                            answer="[답변 생성 실패]"
                        )
                    }

            prompt2 = getattr(self.templates, f"answer{node_id}_prompt").format(
                question=question,
                til=state.til,
                level=state.level,
            )
            prompt2 = self.sanitize_prompt(prompt2)

            try:
                final_text = await asyncio.wait_for(
                    self.llm.answer_generate(prompt2),
                    timeout=30
                )
                final_text = self.delete_blank(final_text)
                
                return {
                    f"content{node_id}":ContentState(
                        question=question,
                        answer=final_text
                    )
                }

            except asyncio.TimeoutError:
                logger.error(f"❗답변 생성 {node_id} 타임아웃")
                return {
                    f"content{node_id}": ContentState(
                        question=question,
                        answer="[답변 생성 타임아웃]"
                    )
                }

            except Exception as e:
                logger.error(f"답변 생성 실패: {e}")
                return {
                    f"content{node_id}":ContentState(
                        question=question,
                        answer="답변 생성 실패"
                    )
                }

        return answer_node

    def is_invalid_summary(self, text: str) -> bool:
        text = text.strip()
        if not text or len(text)>30:
            return True
        if text in ["###", "Q:", "제목 없음"]:
            return True
        if text.lower().startswith("q:") or text.lower().startswith("a:"):
            return True
        if text in ["###", "제목:", "제목 없음"]:
            return True
        return False

    @traceable(name="요약 생성 노드", run_type="llm")
    async def summary_node(self, state: QAState) -> dict:
        merged = []
        for i in range(3):
            item = getattr(state, f"content{i}", None)
            if item:
                merged.append(item)

        qacombined = "\n".join(
            f"Q: {item.question}\nA: {item.answer}" for item in merged
        )

        prompt3 = self.templates.summary.format(
            qacombined = qacombined
        )
        prompt3 = self.sanitize_prompt(prompt3)

        last_valid = None

        for attempt in range(3):
            try:
                final_text = await asyncio.wait_for(
                    self.llm.summary_generate(prompt3),
                    timeout=10
                )

                final_text = self.delete_blank(final_text).strip()

                if not final_text or final_text in ["###", "[요약 실패]"]:
                    logger.warning(f"요약 시도 {attempt+1} 실패한 출력: {final_text}")
                    continue

                if not self.is_invalid_summary(final_text):
                    return {
                        "summary": final_text,
                        "content": merged
                    }

                last_valid = final_text

                return {
                    "summary": final_text,
                    "content": merged
                }
            except Exception as e:
                logger.warning(f"요약 시도 {attempt+1} 실패: {e}")
                continue
        
        logger.error("요약 생성 3회 실패")
        return {
            "summary": last_valid or "[요약 실패]",
            "content": merged
        }
        
    def build_graph(self):
        workflow = StateGraph(QAState)

        async def start_node(state: QAState) -> dict:
            return {}
        
        workflow.add_node("start", start_node)
        workflow.set_entry_point("start")

        for i in range(3):
            workflow.add_node(f"que{i}", self.generate_question_node(i))
            workflow.add_node(f"ans{i}", self.generate_answer_node(i))

            workflow.add_edge("start", f"que{i}")
            workflow.add_edge(f"que{i}", f"ans{i}")
            workflow.add_edge(f"ans{i}", "summary_generate")

        workflow.add_node("summary_generate", self.summary_node)
        workflow.set_finish_point("summary_generate")

        return workflow.compile()