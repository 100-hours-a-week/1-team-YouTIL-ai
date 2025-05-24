from tenacity import retry, stop_after_attempt, wait_fixed
from langgraph.graph import StateGraph
from sentence_transformers import SentenceTransformer
from uuid import uuid4
from vllm import SamplingParams
from schemas import QAState, ContentState
import logging
import re

logger = logging.getLogger(__name__)

# @retry(stop=stop_after_attempt(2), wait=wait_fixed(1))
# async def wrap_llm_generate(llm, prompt, sampling_params) -> str:
#     request_id = str(uuid4())
#     try:
#         logger.info(f"LLM 호출")

#         async for output in llm.generate(
#             prompt=prompt,
#             sampling_params=sampling_params,
#             request_id=request_id
#         ):
#             return output.outputs[0].text.strip()

#     except Exception as e:
#         logger.error(f"❌ LLM 호출 실패 | prompt 일부: {prompt[:40]}... | error: {e}")
#         raise e

class QAFlow:
    def __init__(self, llm, qdrant, templates):
        self.llm = llm
        self.qdrant = qdrant
        self.templates = templates
        self.embedding_model = SentenceTransformer("BAAI/bge-m3", device="cpu")

    def embed_text(self, text: str) -> list[float]:
        return self.embedding_model.encode(text).tolist()

    async def retriever_node(self, state: QAState) -> dict:
        query = state.title + " " + " ".join(state.keywords)
        query_vector = self.embed_text(query)

        category = state.category 

        results = self.qdrant.search(
            collection_name=category,
            query_vector=query_vector,
            limit=3,
            with_payload=True
        )

        retrieved_texts = [r.payload["text"] for r in results if "text" in r.payload]
        best_score = results[0].score if results else 0.0

        return {
            "similarity_score": best_score,
            "retrieved_texts": retrieved_texts
        }
    
    # 후처리 추가 
    def clean_korean_question(self, text: str) -> str:

        text = re.sub(r'\*\*(.*?)\*\*', r'\1', text)

        # 라벨 및 마크다운 제거
        text = re.sub(r'\*\*?(Question|Answer|Note|Level).*?\*\*?', '', text, flags=re.IGNORECASE)
        text = re.sub(r'(Question|Answer|Level)\s*[:：]*', '', text, flags=re.IGNORECASE)
        text = re.sub(r'^#+\s*', '', text)

        # 문장 맨 앞 하이픈/번호 제거
        text = re.sub(r'^[-•\s]+\d*\s*', '', text)

        # 괄호 level (띄어쓰기 포함) 제거
        text = re.sub(r'\(\s*\d+\s*\)', '', text)

        # 기타 특수문자 제거
        text = text.replace("`", "").replace("“", "").replace("”", "")
        text = text.replace("👉", "").replace("→", "").strip()
        text = text.strip().strip('"“”')

        # 줄 단위로 나누기
        lines = [line.strip() for line in text.split('\n') if line.strip()]

        question_endings = ["?", "요.", "습니까", "설명해주세요", "어떻게", "무엇", 
                            "설명하시오", "구현하시오", "알려주세요", "어떤가요", "왜 그런가요"]
        
        # 완결된 질문형 문장만 탐색
        for line in lines:
            if any(ending in line for ending in question_endings):
                return line

        return lines[0] if lines else ""


    def generate_question_node(self, node_id: int):
        async def question_node(state: QAState) -> dict:
            retrieved = "\n\n".join(state.retrieved_texts or [])
            
            prompt1 = getattr(self.templates, f"question{node_id}_prompt").format(
                til=state.til,
                level=state.level,
                retrieved=retrieved
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

            # final_text = await wrap_llm_generate(self.llm, prompt1, sampling_params)

            cleaned_question = self.clean_korean_question(final_text)

            return {f"question{node_id}": cleaned_question}

        return question_node

    def generate_answer_node(self, node_id: int):
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
                #raise ValueError(f"질문 {node_id}가 없습니다.")

            context = "\n\n".join(state.retrieved_texts or [])

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
            
            # final_text = await wrap_llm_generate(self.llm, prompt2, sampling_params)

            return {
                f"content{node_id}": ContentState(
                    question=question,
                    answer=final_text
                )
            }

        return answer_node

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

        # final_text = await wrap_llm_generate(self.llm, prompt3, sampling_params)


        return {
            "summary": final_text,
            "content": merged
        }

    def build_graph(self):
        workflow = StateGraph(QAState)
        workflow.set_entry_point("retriever")
        workflow.add_node("retriever", self.retriever_node)

        for i in range(3):
            workflow.add_node(f"que{i}", self.generate_question_node(i))
            workflow.add_node(f"ans{i}", self.generate_answer_node(i))

            workflow.add_edge("retriever", f"que{i}")
            workflow.add_edge(f"que{i}", f"ans{i}")
            workflow.add_edge(f"ans{i}", "summary_generate")

        workflow.add_node("summary_generate", self.summary_node)
        workflow.set_finish_point("summary_generate")

        return workflow.compile()