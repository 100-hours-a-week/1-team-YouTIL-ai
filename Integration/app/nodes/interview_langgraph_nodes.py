from tenacity import retry, stop_after_attempt, wait_fixed
from langgraph.graph import StateGraph
from langsmith import traceable
from app.schemas.Interview_Schema import QAState, ContentState
from app.models.interview_model import model
import logging
import re

logger = logging.getLogger(__name__)

class QAFlow:
    def __init__(self, llm, qdrant, templates):
        self.llm = llm
        self.qdrant = qdrant
        self.templates = templates
        self.embedding_model = model.embedder

    def embed_text(self, text: str) -> list[float]:
        return self.embedding_model.encode(text).tolist()
    
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

    def generate_question_node(self, node_id: int):
        @traceable(name=f"질문 생성 노드 {node_id}", run_type="llm")
        async def question_node(state: QAState) -> dict:
            prompt1 = getattr(self.templates, f"question{node_id}_prompt").format(
                til=state.til,
                level=state.level,
            )

            try:
                final_text = await model.generate_gemini(
                    prompt=prompt1,
                    max_tokens=128,
                    temperature=0.5
                )

                cleaned_question = self.clean_korean_question(final_text)
                return {f"question{node_id}": cleaned_question}
            
            except Exception as e:
                logger.error(f"질문 생성 실패: {e}")
                return {f"question{node_id}": ""}

        return question_node
    
    def generate_retriever_node(self, node_id: int):
        @traceable(name=f"검색 노드 {node_id}", run_type="retriever")
        async def retriever_node(state: QAState) -> dict:
            question = getattr(state, f"question{node_id}", "")
            query = f"{state.til}\n{question}"
            query_vector = self.embed_text(query)

            results = self.qdrant.search(
                collection_name="tavily_docs",
                query_vector=query_vector,
                limit=1,
                with_payload=True
            )

            retrieved_texts = [r.payload["text"] for r in results if "text" in r.payload]
            best_score = results[0].score if results else 0.0

            return {
                f"similarity_score{node_id}": best_score,
                f"retrieved_texts{node_id}": retrieved_texts
            }
        
        return retriever_node

    def delete_blank(self, text: str) -> str:
        # 1. 수평선 "---" 제거 (줄 단독이거나 앞뒤 개행 포함된 경우)
        text = re.sub(r"(?m)^\s*---+\s*$", "", text)

        # 2. 코드블록 마크다운 제거: ``` 또는 ```markdown
        text = re.sub(r"```(?:markdown)?", "", text)

        # 3. \n과 헤더 사이가 붙어 있을 경우 \n\n으로 보정
        text = re.sub(r"(?<!\n)\n(###)", r"\n\n\1", text)

        # 4. 헤더 아닌 줄은 들여쓰기 제거
        lines = text.splitlines()
        cleaned_lines = [
            line if line.startswith("###") or line.strip() == "" else line.lstrip()
            for line in lines
        ]

        # 5. 불필요한 연속 개행 제거 (최대 2줄까지만 허용)
        cleaned_text = "\n".join(cleaned_lines)
        cleaned_text = re.sub(r"\n{3,}", "\n\n", cleaned_text)

        return cleaned_text.strip()

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

            context = getattr(state, f"retrieved_texts{node_id}", None)
            context = "\n\n".join(context) if context else ""

            prompt2 = getattr(self.templates, f"answer{node_id}_prompt").format(
                question=question,
                til=state.til,
                level=state.level,
                context=context
            )

            try:
                final_text = await model.generate_gemini(
                    prompt=prompt2,
                    max_tokens=512,
                    temperature=0.3,
                )

                final_text = self.delete_blank(final_text)
                
                return {
                    f"content{node_id}":ContentState(
                        question=question,
                        answer=final_text
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

        last_valid = None

        for attempt in range(3):
            try:
                final_text = await model.generate_gemini(
                    prompt=prompt3,
                    max_tokens=32,
                    temperature=0.3
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
            workflow.add_node(f"retriever{i}", self.generate_retriever_node(i))
            workflow.add_node(f"ans{i}", self.generate_answer_node(i))

            workflow.add_edge("start", f"que{i}")
            workflow.add_edge(f"que{i}", f"retriever{i}")
            workflow.add_edge(f"retriever{i}", f"ans{i}")
            workflow.add_edge(f"ans{i}", "summary_generate")

        workflow.add_node("summary_generate", self.summary_node)
        workflow.set_finish_point("summary_generate")

        return workflow.compile()