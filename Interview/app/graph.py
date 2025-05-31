from tenacity import retry, stop_after_attempt, wait_fixed
from langgraph.graph import StateGraph
from langsmith import traceable
from uuid import uuid4
from vllm import SamplingParams
from schemas import QAState, ContentState
from model import model
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

        # 라벨 및 마크다운 제거
        text = re.sub(r'\*\*?(Question|Answer|Note|Level).*?\*\*?', '', text, flags=re.IGNORECASE)
        text = re.sub(r'(Question|Answer|Level)\s*[:：]*', '', text, flags=re.IGNORECASE)
        text = re.sub(r'^#+\s*', '', text)

        # 문장 맨 앞 하이픈/번호 제거
        text = re.sub(r'^[-•\s]+\d*\s*', '', text)

        # 기타 특수문자 제거
        text = text.replace("`", "").replace("“", "").replace("”", "")
        text = text.replace("👉", "").replace("→", "").strip()
        text = text.strip().strip('"“”')

        # 줄 단위로 나누기
        lines = [line.strip() for line in text.split('\n') if line.strip()]

        return lines[0] if lines else ""

    def generate_question_node(self, node_id: int):
        @traceable(name=f"질문 생성 노드 {node_id}", run_type="llm")
        async def question_node(state: QAState) -> dict:
            prompt1 = getattr(self.templates, f"question{node_id}_prompt").format(
                til=state.til,
                level=state.level,
            )

            sampling_params = SamplingParams(
                temperature=0.7,
                max_tokens=128,
                stop_token_ids=[2]
            )

            request_id = str(uuid4())
            final_text = ""

            async for output in self.llm.generate(
                prompt=prompt1,
                sampling_params=sampling_params,
                request_id=request_id
            ):
                final_text = output.outputs[0].text.strip()

            cleaned_question = self.clean_korean_question(final_text)

            return {f"question{node_id}": cleaned_question}

        return question_node
    
    def generate_retriever_node(self, node_id: int):
        @traceable(name=f"검색 노드 {node_id}", run_type="retriever")
        async def retriever_node(state: QAState) -> dict:
            question = getattr(state, f"question{node_id}", "")
            query = f"{state.til}\n{question}"
            query_vector = self.embed_text(query)

            results = self.qdrant.search(
                collection_name="knowledge_all",
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

            sampling_params = SamplingParams(
                temperature=0.7,
                max_tokens=512,
                stop_token_ids=[2]
            )

            request_id = str(uuid4())
            final_text = ""

            async for output in self.llm.generate(
                prompt=prompt2,
                sampling_params=sampling_params,
                request_id=request_id
            ):
                final_text = output.outputs[0].text.strip()

            return {
                f"content{node_id}": ContentState(
                    question=question,
                    answer=final_text
                )
            }

        return answer_node

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

        sampling_params = SamplingParams(
            temperature=0.3,
            max_tokens=32,
            stop_token_ids=[2]
        )

        request_id = str(uuid4())
        final_text = ""

        async for output in self.llm.generate(
            prompt=prompt3,
            sampling_params=sampling_params,
            request_id=request_id
        ):
            final_text = output.outputs[0].text.strip()

        return {
            "summary": final_text,
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
    
