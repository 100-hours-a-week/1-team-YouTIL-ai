import json
from typing import Dict
from openai import OpenAI
import pymysql

class TilEvaluator:
  def __init__(self, open_api_key: str, content: str):
    self.client = OpenAI(api_key=open_api_key)
    self.content = content

  def evaluate_til(self, content: str) -> str:
    prompt = self.evaluate_prompt(content)
    response = self._get_gpt4_response(prompt)
    return response

  def evaluate_prompt(self, content: str) -> str:
    return f"""당신은 숙련된 개발자이며, AI가 작성한 TIL(Today I Learned) 문서를 비판적 관점에서 평가하는 역할을 맡았습니다.

작성된 TIL의 기술적 완성도, 표현의 정확성, 독자 친화성 등을 다음 항목에 따라 1점에서 10점 사이로 엄격하게 평가하세요.

각 항목마다 **구체적인 기술 개념**, **누락된 배경**, **서술상 문제** 등을 지적해주고, 점수를 후하게 주지 마십시오. 피상적인 칭찬은 금물입니다.

### 평가 기준:

1. **주제 명확성**: 하나의 중심 주제가 일관되게 전달되었는가? 주제가 흐릿하거나 산만하지 않은가?
2. **학습 동기 서술**: 학습하게 된 이유가 실제 사례나 문제 상황을 기반으로 구체적으로 설명되었는가?
3. **핵심 개념의 정확성**: 기술 개념의 정의, 역할, 사용 맥락이 정확히 설명되었는가? 오용되거나 생략된 것은 없는가?
4. **문장 명료도**: 반복 표현 없이 간결하고 직접적인 문장으로 핵심이 전달되는가?
5. **기술 용어 사용 정확성**: 전문 용어가 정확히 쓰였는가? 불명확하거나 혼동되는 표현은 없는가?
6. **요점 정리 능력**: 중복 없이 각 항목이 새로운 정보를 담고 있는가? 불필요한 설명은 배제되었는가?
7. **개념 간 연계 설명**: 개별 개념들이 논리적으로 연결되어 설명되었는가? 예: index.html → root div → React mount flow 등.
8. **문제 해결 서술력**: 문제 발생의 맥락, 해결 시도, 결과가 구체적으로 서술되었는가?
9. **문서 구조의 완성도**: 문단, 소제목, 섹션 분리가 명확하며 정보가 구조적으로 배열되었는가?
10. **마크다운 형식 일관성**: 문법 오류 없이 일관된 형식으로 마크다운이 작성되었는가?
11. **재사용 가능성**: 다른 개발자도 그대로 참고할 수 있을 정도로 실용적인 예시나 설명이 있는가?
12. **실용적 학습 가치**: 당일 학습 내용이 현업에서 실제 도움이 되는가? 단순 정리가 아닌 실제 팁이나 인사이트가 담겼는가?
13. **독자 친화성**: 배경 지식이 부족한 독자도 이해할 수 있도록 보충 설명이나 용어 정의가 적절한가?

---

### 지침

- 항목별 점수는 반드시 **근거와 함께** 제시하십시오.
- `좋습니다`, `잘했습니다`와 같은 일반적 표현은 피하고, **무엇이 왜 부족했는지**, **어떻게 개선해야 하는지** 구체적으로 서술하십시오.
- 모든 응답은 반드시 아래 JSON 형식에 따르십시오.

---

[평가 대상 TIL 문서]
{content}

[응답 형식 (JSON)]:

{{
  "scores": {{
    "주제 명확성": {{
      "score": 0,
      "explanation": ""
    }},
    "학습 동기 서술": {{
      "score": 0,
      "explanation": ""
    }},
    "핵심 개념의 정확성": {{
      "score": 0,
      "explanation": ""
    }},
    "문장 명료도": {{
      "score": 0,
      "explanation": ""
    }},
    "기술 용어 사용 정확성": {{
      "score": 0,
      "explanation": ""
    }},
    "요점 정리 능력": {{
      "score": 0,
      "explanation": ""
    }},
    "개념 간 연계 설명": {{
      "score": 0,
      "explanation": ""
    }},
    "문제 해결 서술력": {{
      "score": 0,
      "explanation": ""
    }},
    "문서 구조의 완성도": {{
      "score": 0,
      "explanation": ""
    }},
    "마크다운 형식 일관성": {{
      "score": 0,
      "explanation": ""
    }},
    "재사용 가능성": {{
      "score": 0,
      "explanation": ""
    }},
    "실용적 학습 가치": {{
      "score": 0,
      "explanation": ""
    }},
    "독자 친화성": {{
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
              total_score = sum(score_info.get("score", 0) for score_info in parsed["scores"].values())
              parsed["total_score"] = total_score

          return parsed

      except Exception as e:
          print(f"Error: 응답을 JSON으로 구문 분석할 수 없습니다. Response: {response[:100]}...")
          return None
          
  @staticmethod
  def insert_til_evaluation_to_db(evaluation: dict, metadata: dict, connection_info: dict):
      conn = pymysql.connect(
          host=connection_info["host"],
          user=connection_info["user"],
          password=connection_info["password"],
          database=connection_info["database"],
          charset='utf8mb4'
      )
      try:
          with conn.cursor() as cursor:
              sql = """
              INSERT INTO til_evaluations (
                  username, commit_date, repo, til_content,
                  total_score, overall_evaluation, improvement_suggestions,

                  topic_clarity_score, topic_clarity_explanation,
                  motivation_score, motivation_explanation,
                  core_concepts_score, core_concepts_explanation,
                  clarity_score, clarity_explanation,
                  terminology_score, terminology_explanation,
                  summarization_score, summarization_explanation,
                  conceptual_linking_score, conceptual_linking_explanation,
                  problem_solving_score, problem_solving_explanation,
                  structure_score, structure_explanation,
                  markdown_consistency_score, markdown_consistency_explanation,
                  reusability_score, reusability_explanation,
                  practical_value_score, practical_value_explanation,
                  reader_friendliness_score, reader_friendliness_explanation
              ) VALUES (
                  %(username)s, %(commit_date)s, %(repo)s, %(til_content)s,
                  %(total_score)s, %(overall_evaluation)s, %(improvement_suggestions)s,

                  %(topic_clarity_score)s, %(topic_clarity_explanation)s,
                  %(motivation_score)s, %(motivation_explanation)s,
                  %(core_concepts_score)s, %(core_concepts_explanation)s,
                  %(clarity_score)s, %(clarity_explanation)s,
                  %(terminology_score)s, %(terminology_explanation)s,
                  %(summarization_score)s, %(summarization_explanation)s,
                  %(conceptual_linking_score)s, %(conceptual_linking_explanation)s,
                  %(problem_solving_score)s, %(problem_solving_explanation)s,
                  %(structure_score)s, %(structure_explanation)s,
                  %(markdown_consistency_score)s, %(markdown_consistency_explanation)s,
                  %(reusability_score)s, %(reusability_explanation)s,
                  %(practical_value_score)s, %(practical_value_explanation)s,
                  %(reader_friendliness_score)s, %(reader_friendliness_explanation)s
              )
              """
              row_data = {
                  **metadata,  # username, commit_date, repo
                  "til_content": metadata["content"],
                  "total_score": evaluation["total_score"],
                  "overall_evaluation": evaluation["overall_evaluation"],
                  "improvement_suggestions": evaluation["improvement_suggestions"],
              }

              for k, v in evaluation["scores"].items():
                  col_prefix = {
                      "주제 명확성": "topic_clarity",
                      "학습 동기 서술": "motivation",
                      "핵심 개념의 정확성": "core_concepts",
                      "문장 명료도": "clarity",
                      "기술 용어 사용 정확성": "terminology",
                      "요점 정리 능력": "summarization",
                      "개념 간 연계 설명": "conceptual_linking",
                      "문제 해결 서술력": "problem_solving",
                      "문서 구조의 완성도": "structure",
                      "마크다운 형식 일관성": "markdown_consistency",
                      "재사용 가능성": "reusability",
                      "실용적 학습 가치": "practical_value",
                      "독자 친화성": "reader_friendliness"
                  }[k]

                  row_data[f"{col_prefix}_score"] = v["score"]
                  row_data[f"{col_prefix}_explanation"] = v["explanation"]

              cursor.execute(sql, row_data)
              conn.commit()
              print("✅ 데이터 삽입 완료")

      finally:
          conn.close()