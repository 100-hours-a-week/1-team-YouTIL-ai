from vllm import AsyncEngineArgs, AsyncLLMEngine
from qdrant_client import QdrantClient
from dotenv import load_dotenv
import os

load_dotenv()

base_llm = os.getenv("MODEL_PATH")

engine_args = AsyncEngineArgs(
    model=base_llm,
    tensor_parallel_size=1, # GPU 개수
    gpu_memory_utilization=0.95,
    max_num_seqs = 100, # 동시에 받을 수 있는 요청 개수
    max_model_len=4096, # input + output 토큰 길이
    max_num_batched_tokens=8192) # 한 batch 당 토근 길이 

llm = AsyncLLMEngine.from_engine_args(engine_args)

qdrant = QdrantClient(
    host=os.getenv("QDRANT_HOST"), 
    port=os.getenv("QDRANT_PORT"))



# 확인용
# os.environ["LANGSMITH_TRACING"]  
# print(os.getenv("QDRANT_HOST"))
# print(os.getenv("QDRANT_PORT"))





prompt1 = """
You are a technical interviewer AI.

Your task is to generate exactly one interview question written in Korean, based on the following inputs:

- Level: {level}
- User TIL: {til}
- Reference documents: {retrieved}

## Output Instructions (strict):
- Your response must be a **single complete sentence** in **Korean**.
- The sentence must be a **clear interview-style question**, using natural question forms such as:
  “~입니까?”, “~있나요?”, “~설명해주세요”, “~어떻게 되나요?”, “~어떻게 생각하시나요?” etc.
- It must **not** be a declarative or answer-style sentence (e.g., ending with “~입니다”, “~합니다” ❌)

- ⚠️ Do NOT include any of the following:
  - English words or explanations
  - Headings, notes, or comments
  - Labels such as “Question:”, “Answer:”, “Note:”, or anything similar
  - Markdown symbols (e.g., **, ``, →, #, ##)
  - Emojis, quotation marks, parentheses, or line breaks

- Only write the Korean question sentence. Nothing else.

## Depth Control:
- Level 1: Ask about deep technical understanding and implementation logic
- Level 2: Ask about conceptual understanding
- Level 3: Ask about basic theoretical concepts

Respond with only one clean Korean question sentence. No explanations, no formatting, no extra text.

question:

"""

prompt2 = """
You are an AI assistant that answers a technical interview question based on the user's learning record.

Here is the input:
- Question: {question}
- User TIL: {til}
- Level: {level}
- Reference documents: {context}

Do not repeat the question.  
Generate **only one answer**, in **Korean**, based on the above information.  
Keep your answer **concise**, **clear**, and **free of unnecessary symbols** or decorations.

Just provide the answer in plain Korean. No introduction or explanation is needed.

answer:

"""

prompt3 = """
You are an AI assistant that summarizes a technical interview question and its answer into a short, meaningful Korean title.

Your goal is to create a clear and specific title that would fit well in a developer document or a technical spec.

Requirements:
- The title must be written in **Korean**
- The title must be **15 characters or fewer**
- Do NOT include any quotation marks, punctuation, or extra lines
- Write only the final title

Example:
Q: REST API란 무엇인가요?  
A: REST API는 HTTP 프로토콜을 기반으로 자원을 URI로 표현하고, CRUD를 HTTP 메서드로 수행하는 아키텍처입니다.  
title: REST API 개념 및 구성 요소

Now summarize the following Q&A in the same way.

{qacombined}

title:

"""




from pydantic import BaseModel
from typing import List, Optional, Dict, Any

class ContentState(BaseModel):
    question: str
    answer: str 

class QAState(BaseModel):
    email: str
    date: str
    level: int
    title: str
    keywords: List[str]
    til: str

    retrieved_texts: Optional[List[str]] = None
    similarity_score: Optional[float] = None

    question0: Optional[str] = None
    question1: Optional[str] = None
    question2: Optional[str] = None

    question: Optional[str] = None
    answer: Optional[str] = None

    content0: Optional[ContentState] = None
    content1: Optional[ContentState] = None
    content2: Optional[ContentState] = None

    #output
    content: Optional[List[ContentState]] = None
    summary: Optional[str] = None


# qa_input = QAState(
#     email=dummy['email'],
#     date=dummy['date'],
#     level=dummy['level'],
#     title=dummy['title'],
#     keywords=dummy['keywords'],
#     til=dummy['til']
# )



from langgraph.graph import StateGraph
from sentence_transformers import SentenceTransformer
from uuid import uuid4
from vllm import SamplingParams
import re

class QAFlow:
    def __init__(self, llm, qdrant, prompt1, prompt2, prompt3, max_nodes=3):
        self.llm = llm
        self.qdrant = qdrant
        self.prompt1 = prompt1
        self.prompt2 = prompt2
        self.prompt3 = prompt3
        self.max_nodes = max_nodes
        self.embedding_model = SentenceTransformer("BAAI/bge-m3", device="cpu")

    def embed_text(self, text: str) -> list[float]:
        return self.embedding_model.encode(text).tolist()

    async def retriever_node(self, state: QAState) -> dict:
        query = state.title + " " + " ".join(state.keywords)
        query_vector = self.embed_text(query)

        collection_names = ["ai", "cloud", "frontend", "backend"]
        best_score = 0.0
        retrieved_texts = []

        for col in collection_names:
            results = self.qdrant.search(
                collection_name=col,
                query_vector=query_vector,
                limit=3,
                with_payload=True
            )
            if results and results[0].score > best_score:
                best_score = results[0].score
                retrieved_texts = [r.payload["text"] for r in results if "text" in r.payload]

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
            
            prompt1 = self.prompt1.format(
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

            cleaned_question = self.clean_korean_question(final_text)

            # print(node_id, final_text)
            # print(node_id, cleaned_question)

            return {f"question{node_id}": cleaned_question}

        return question_node

    def generate_answer_node(self, node_id: int):
        async def answer_node(state: QAState) -> dict:
            question = getattr(state, f"question{node_id}", None)
            if not question:
                raise ValueError(f"질문 {node_id}가 없습니다.")

            context = "\n\n".join(state.retrieved_texts or [])

            prompt2 = self.prompt2.format(
                question=question,
                til=state.til,
                level=state.level,
                context=context
            )

            sampling_params = SamplingParams(
                temperature=0.7,
                max_tokens=256,
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
                #"content": [ContentState(question=question, answer=final_text)]
                f"content{node_id}": ContentState(
                    question=question,
                    answer=final_text)
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

        prompt3 = self.prompt3.format(
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
        workflow.set_entry_point("retriever")
        workflow.add_node("retriever", self.retriever_node)

        for i in range(self.max_nodes):
            workflow.add_node(f"que{i}", self.generate_question_node(i))
            workflow.add_node(f"ans{i}", self.generate_answer_node(i))

            workflow.add_edge("retriever", f"que{i}")
            workflow.add_edge(f"que{i}", f"ans{i}")
            workflow.add_edge(f"ans{i}", "summary_generate")

        workflow.add_node("summary_generate", self.summary_node)
        workflow.set_finish_point("summary_generate")

        return workflow.compile()





qa_flow = QAFlow(llm=llm, qdrant=qdrant, prompt1=prompt1, prompt2=prompt2, prompt3=prompt3, max_nodes=3)
graph = qa_flow.build_graph()
# result = await graph.ainvoke(qa_input)

# # 결과 출력
# print(result["summary"])

# for c in result["content"]:
#     print(c.question)
#     print(c.answer)
#     print()




from fastapi import FastAPI
import traceback
#from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

app = FastAPI(debug=True)

@app.post("/generate")
async def generate(data: QAState):
    try:
        result = await graph.ainvoke(data)
        return result
    except Exception as e:
        traceback.print_exc()
        return JSONResponse(status_code=500, content={"error": str(e)})


