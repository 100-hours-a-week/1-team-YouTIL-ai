import json
from typing import Dict
from openai import OpenAI
import os

open_api_key = os.getenv("OPENAI_API_KEY")

class InterviewEvaluator:
  def __init__(self, open_api_key: str):
    self.client = OpenAI(api_key=open_api_key)

  def evaluate_interview(self, til: str, question: str, context: str, answer: str) -> dict:
    prompt = self.evaluate_prompt(til, question, context, answer)
    response = self._get_gpt4_response(prompt)
    if response:
        return self._parsed_evaluation(response)
    return None

  def evaluate_prompt(self, til: str, question: str, context:str, answer: str) -> str:
    return f"""
당신은 TIL(Today I Learned)을 기반으로 생성된 인터뷰 질문과 답변을 평가하는 AI 평가자입니다.  
다음은 한 개발자의 TIL 기록, 해당 내용을 기반으로 생성된 질문/답변, 그리고 RAG 기반으로 검색된 문서들입니다.  
당신의 역할은 아래 기준에 따라 **1점에서 10점 사이의 점수와 구체적인 피드백**을 제공하는 것입니다.

### 평가 기준 (각 항목 1점 ~ 10점):

1. **TIL 반영도**
    - 질문과 답변이 TIL에서 학습한 핵심 개념, 경험, 배경을 실제로 반영했는가?  
    - TIL과 무관한 내용으로 질문이 유도되지는 않았는가?
2. **사실 정확성**
   - 답변이 기술적으로 정확한가?  
   - 잘못된 설명, 할루시네이션, 과도한 일반화는 없는가?
3. **검색 기반 근거 활용도**
   - 검색된 문서에서 유의미한 정보가 실제 답변에 반영되었는가?  
   - 단순 검색 결과 나열이 아닌, 적절한 지식 기반 응답으로 연결되었는가?
4. **답변 완성도**
   - 구조적이고 명확하며, 충분한 길이와 설득력을 갖춘 인터뷰 답변인가?  
   - 핵심 논리 흐름이 부족하거나, 비약/반복은 없는가?
5. **난이 적절성**
   - 질문이 TIL 수준과 적절히 대응하며, 실제 인터뷰 상황에 적합한 깊이와 범위를 가졌는가?  
   - 과도하게 단순하거나 불필요하게 복잡하진 않은가?

---

### 지침

- 항목별 점수는 반드시 **근거와 함께** 제시하십시오.
- `좋습니다`, `잘했습니다`와 같은 일반적 표현은 피하고, **무엇이 왜 부족했는지**, **어떻게 개선해야 하는지** 구체적으로 서술하십시오.
- 모든 응답은 반드시 아래 JSON 형식에 따르십시오.

---

[평가 대상 TIL 내용]
{til}

[생성된 질문]
{question}

[생성된 답변]
{answer}

[검색된 문서 요약]
{context}

[응답 형식 (JSON)]:

{{
  "scores": {{
    "TIL 반영도": {{
      "score": 0,
      "explanation": ""
    }},
    "사실 정확성": {{
      "score": 0,
      "explanation": ""
    }},
    "검색 기반 근거 활용도": {{
      "score": 0,
      "explanation": ""
    }},
    "답변 완성도": {{
      "score": 0,
      "explanation": ""
    }},
        "난이도 적절성": {{
      "score": 0,
      "explanation": ""
    }}
  }},
  "total_score": 0,
  "overall_evaluation": "",
  "improvement_suggestions": ""
}}
"""

  def _get_gpt4_response(self, prompt: str) -> str:
    try:
      response = self.client.chat.completions.create(
        model="gpt-4o-mini",
        response_format={ "type": "json_object" },
        messages=[{"role": "system", "content": prompt}],
        temperature=0.1
      )
      return response.choices[0].message.content
    except Exception as e:
      print(f"Error in API call: {e}")
      return None

  def _parsed_evaluation(self, response: str) -> Dict:
      try:
          parsed = json.loads(response)

          # scores 내부 점수 합산하여 total_score 재계산
          if "scores" in parsed:
              total_score = sum(float(score_info.get("score", 0)) for score_info in parsed["scores"].values())
              parsed["total_score"] = total_score

              # Flatten scores into top-level keys
              for k, v in parsed["scores"].items():
                  if k == "TIL 반영도":
                      parsed["til_relevance_score"] = v["score"]
                      parsed["til_relevance_explanation"] = v["explanation"]
                  elif k == "사실 정확성":
                      parsed["factual_accuracy_score"] = v["score"]
                      parsed["factual_accuracy_explanation"] = v["explanation"]
                  elif k == "검색 기반 근거 활용도":
                      parsed["retrieval_grounding_score"] = v["score"]
                      parsed["retrieval_grounding_explanation"] = v["explanation"]
                  elif k == "답변 완성도":
                      parsed["answer_quality_score"] = v["score"]
                      parsed["answer_quality_explanation"] = v["explanation"]
                  elif k == "난이도 적절성":
                      parsed["difficulty_fit_score"] = v["score"]
                      parsed["difficulty_fit_explanation"] = v["explanation"]

          return parsed

      except Exception as e:
          print(f"Error: 응답을 JSON으로 구문 분석할 수 없습니다. Response: {response[:100]}...")
          return None