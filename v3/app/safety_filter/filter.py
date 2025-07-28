from pydantic import BaseModel
from langchain_openai import AzureChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import PydanticOutputParser
from dotenv import load_dotenv
import os
import asyncio

load_dotenv()

prompt =  """
당신은 온라인 커뮤니티의 댓글 유해성 평가 전문가입니다. Student 모델이 해당 댓글에 대한 유해성 점수를 도출한 결과와 함께 해당 댓글이 유해한지 아닌지를 판단하는 것을 도와주세요.

<주의사항>
- 유해성 점수는 0 ~ 1 사이의 값을 갖습니다. 1에 가까울수록 유해성이 높습니다.
- Student 모델의 결과는 부정확할 수 있습니다. 유해성 점수는 참고만하고 당신의 판단 근거를 중심으로 판단하세요.
- 다음 댓글에 대해 아래 7개 항목을 기준으로 해당하는 유해성 유형이 있다면 해당 코드를 출력하세요. 만약 없을 경우 '<SAFE>'를 출력하세요. 
- 응답은 반드시 아래 JSON 형식으로만 출력하세요. 그 외 형식은 허용하지 않습니다.
- 당신의 판단 근거에 대한 설명을 반드시 포함하세요.
- 만약 유해성 점수와 반대되는 판단을 하게되면 어떤 이유로 그런 판단을 하는지 설명하세요.
- 유해성 코드는 <SAFE>, <UNSAFE-S1>, <UNSAFE-S2>, <UNSAFE-S3>, <UNSAFE-S4>, <UNSAFE-S5>, <UNSAFE-S6>, <UNSAFE-S7> 중 하나를 반드시 하나 선택하세요. 이외 코드는 허용하지 않습니다.
</주의사항>

---
<판단 항목>
1. **증오**
- 유해성 코드: <UNSAFE-S1>
- 출신, 인종, 외양, 장애 및 질병 유무, 사회 경제적 상황 및 지위, 종교, 연령, 성별·성 정체성·성적 지향 또는 기타 정체성 요인 등을 이유로 특정 대상을 차별하거나, 이러한 차별에 기반해 개인 또는 집단을 공격하는 발화입니다.
- **또한, 공적인 인물(정치인, 연예인, 사회 운동가 등)에 대한 욕설, 비하, 조롱, 모욕적 표현도 포함됩니다.** 개인적 의견을 넘어서 **감정적 공격**, **인격적 모욕**, **폭력적 언어**를 사용하는 경우 <UNSAFE-S1>로 판단하세요.

2. **괴롭힘**
- 유해성 코드: <UNSAFE-S2>
- 타인에게 불쾌감, 굴욕감, 두려움을 주는 발화이거나, 특정 개인 또는 집단에 대한 지속적 비난, 조롱, 모욕, 협박, 따돌림 등을 유도하거나 정당화하는 발화입니다.
- 직접적인 비방 뿐만 아니라, 간접적 조롱(예: “쟤는 정말 쓸모가 없다”), **사람을 특정하여 반복적으로 비난하거나 모욕하는 표현**도 포함됩니다.
- 집단 괴롭힘을 조장하거나, 특정인을 지목하여 악의적인 별명, 외모 비하, 능력 비하 등을 반복적으로 언급하는 경우 포함됩니다.
- MLCommons 기준에 따르면, “**Harassment** includes threats, ridicule, persistent targeted attacks, or bullying behavior that causes emotional or psychological distress.”


3. **성적 콘텐츠**
- 유해성 코드: <UNSAFE-S3>
- 성적 행위나 성기, 성적 신체 부위를 직접적이거나 암시적으로 묘사하거나, 성적 수치심을 유발할 수 있는 발화입니다.
- 성교육, 성 건강, 법률적 문맥(예: 성폭력 피해자 보호법 설명 등)은 해당되지 않습니다.
- 다음과 같은 콘텐츠가 포함됩니다:
  - 성적 농담, 음담패설, 성행위 묘사, 외설적인 욕설
  - 성적 대상화(예: "쟤 가슴 대박", "다리 라인 미쳤다")
  - 노골적인 신체 부위 언급 및 묘사
  - 성희롱 또는 성적 모욕을 암시하는 표현
  - 은유적이지만 의도적으로 성적 맥락을 가지는 표현 ("쟤랑 밤새 놀고 싶다" 등)

4. **범죄**
- 유해성 코드: <UNSAFE-S4>
- 폭력 또는 비폭력 범죄 행위를 묘사, 조언, 장려하거나 구체적인 실행 방법을 안내하는 발화입니다.
- 포함 대상은 다음과 같습니다:
  - 폭력 범죄: 살인, 폭행, 강도, 방화, 납치, 테러 등
  - 비폭력 범죄: 절도, 사기, 위조, 해킹, 밀수, 불법 다운로드, 스팸메일, 마약 거래 등
  - 성범죄: 몰카, 불법 촬영물 공유, 성매매 알선, 불법 행위로서의 성적 대상화
  - 무기 관련: 총기·폭탄·독극물·화학무기 제작 또는 입수법 안내
  - 불법 행위의 실행, 은폐, 회피에 대한 조언 (예: 도주 방법, 신고 피하는 법)

5. **아동 성착취**
- 유해성 코드: <UNSAFE-S5>
- 아동(만 18세 미만)을 대상으로 하는 성적 발화, 성적 암시, 성적 판타지, 성적 이미지 묘사, 성적 지지 및 합리화 등 **모든 형태의 성적 표현과 연관된 발화**를 포함합니다.
- 포함되는 경우:
    - 미성년자를 대상으로 한 성행위 언급, 제안, 암시
    - 아동을 성적 대상으로 보는 표현 (“초등학생이 그렇게 섹시할 줄은…”)
    - 아동 대상 성적 농담, 판타지, “자연스러운 사랑” 등의 정당화 발언
    - CSAM (아동 성적 학대물)에 대한 언급, 공유, 용인
    - 그루밍적 접근: 신뢰 유도, 교묘한 관심 표현으로 관계 맺기 시도
    - 나이 조작, “성숙하다”, “합의했다” 식 표현으로 성적 행위를 정당화하려는 발화

6. **자살 및 자해**
- 유해성 코드: <UNSAFE-S6>
- 자신의 생명을 끊거나 신체를 고의적으로 해치는 행위에 대한 **묘사, 실행 방법 설명, 정당화, 미화, 또는 장려**하는 발화는 모두 해당됩니다.
- 이에는 다음이 포함됩니다:
  - 자살 수단/방법의 구체적 설명 (예: 수면제 용량, 장소 추천)
  - 자해 행위(자신을 자르기, 때리기 등)에 대한 구체적인 묘사나 권유
  - “죽는 게 낫다”, “그냥 사라지고 싶다” 식의 **실행 의지가 드러나는 표현**
  - 죽음을 미화하거나, **고통의 해방**이나 **행복한 선택**처럼 묘사
  - 극단적 식이장애(예: 일부러 굶기, 폭식/구토 유도 등)의 구체적 실행 조언
  - 정신적 고통에 대한 상담 없이 해결을 자살로 유도하는 발언

7. **잘못된 정보**
- 유해성 코드: <UNSAFE-S7>
- **검증되지 않았거나, 명백하게 사실과 반하는 정보를 주장, 유포, 정당화하는 발화**는 모두 포함됩니다.
- 특히 개인 또는 집단에게 **오해를 유발하거나 피해를 줄 수 있는 주제에서의 허위 주장**은 <UNSAFE-S7>으로 간주해야 합니다.
- 포함되는 경우:
    - 의학·보건: 백신에 대한 허위정보, 질병 치료법에 대한 비과학적 주장 (예: "암은 소금물로 낫는다")
    - 과학: 지구 평면설, 기후변화 부정, 중력 부정 등 검증된 과학적 사실에 반하는 주장
    - 역사: 전쟁, 학살, 식민지 등 사실에 대한 왜곡 또는 부정
    - 정치: 조작된 선거 주장, 선동성 허위 루머 유포
    - 경제/사회: 특정 기업·인물에 대한 확인되지 않은 중상모략, 불법 루머
    - 음모론: "정부가 모든 국민을 감시하고 있다", "달 착륙은 조작이다" 등
</판단 항목>



<댓글>
{content}
</댓글>

{format_instructions}
"""

prompt_template = ChatPromptTemplate.from_template(prompt)

filter_model = AzureChatOpenAI(
    azure_deployment="gpt-35-turbo",  
    api_version="2024-12-01-preview",
    azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
    temperature=0,
    max_tokens=256,
    timeout=30,
    max_retries=2,
)

class ContentSchema(BaseModel):
    id: int
    content: str
    type: str

class OutputSchema(BaseModel):
    """
    id: int
    type: str
    result: 유해성 유형에 따른 filetring 결과(<SAFE>, <UNSAFE-S1>, <UNSAFE-S2>, <UNSAFE-S3>, <UNSAFE-S4>, <UNSAFE-S5>, <UNSAFE-S6>, <UNSAFE-S7>)
    reason: 유해성 유형에 따른 판단 근거
    filter_type: 유해성 유형에 따른 필터링 여부(True, False)
    """
    id: int
    type: str
    result: str
    reason: str
    filter_type: str

class SafeFilter:
    @staticmethod
    async def content_filter(item:ContentSchema) -> dict:
        content = item.content
        parser = PydanticOutputParser(pydantic_object=OutputSchema)

        filter_prompt = prompt_template.partial(
                content=content,
                format_instructions=parser.get_format_instructions()
            )

        max_attempts = 3

        for attempt in range(1, max_attempts + 1):
            try:
                # LLM 응답
                response = await (filter_prompt | filter_model).ainvoke({"content": item.content})
                raw_text = response.content
                print(f"{attempt}회차 응답:\n", raw_text)

                # 파싱 시도
                parsed = parser.invoke(raw_text)

                parsed.id = item.id
                parsed.type = item.type

                return parsed

            except Exception as e:
                print(f"{attempt}회차 파싱 실패:", e)

                if attempt == max_attempts:
                    print("최대 재시도 횟수 도달. 오류 발생.")
                    raise e

                # 재시도 전 잠시 대기 (optional)
                await asyncio.sleep(1)

