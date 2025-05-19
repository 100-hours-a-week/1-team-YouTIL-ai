class LanggraphPrompts:
    @classmethod
    def make_til_draft(
        cls,
        date: str,
        final,
        ) -> str:
        
        til_prompt = f"""
        다음은 하나 이상의 소스코드 파일에 대한 분석 요약과 변경 이력 분석입니다. 이를 참고하여 마크다운 형식의 TIL을 작성해 주세요.

        [날짜]
        {date}

        [실제 입력]
        - 최근 커밋 메시지: {final["code_changes"][0]["commit_message"]}
        - [코드]: {final["latest_code"]}
        - [삭제된 코드 내용]: {final["code_changes"][0]["before_code"]}
        - [추가된 코드 내용]: {final["code_changes"][0]["after_code"]}

        ⚠️ 출력 규칙:
        - 각 줄은 절대 들여쓰기 없이 시작하세요.
        - 헤더는 `#`, `##`로 시작하고 공백 없이 맨 앞에 위치해야 합니다.
        - 본문도 줄 맨 앞에서 시작해야 하며, 불필요한 공백이나 탭을 포함하지 마세요.
                

        TIL 작성 시 반드시 포함할 항목 (개조식):
        제목: # 📅 날짜 TIL
        ### 📖 1. 오늘 배운 내용

        ### 📚 2. 개념 정리

        ### 🤔 3. 해당 개념이 필요한 이유

        ### 💡 4. 개념을 활용하는 방법

        ### 🛠️ 5. 문제 해결 과정

        ### ✍️ 6. 하루 회고

        작성 시 포함해야 할 항목 외에는 작성하지 마세요. 1번 항목부터 순차적으로 작성하세요. 들여쓰기는 없어야 합니다.
                
        TIL:"""
        return til_prompt
    
    @classmethod
    def til_keywords_prompt(cls, content: str) -> str:
        prompt = f"""
    다음 TIL 내용을 바탕으로 **핵심 키워드 1~3개**를 추출해 주세요.

    요구 조건:
    - 일반적인 단어("공부", "내용", "코드")는 제외하고, 기술적이거나 도메인 관련 키워드만 포함하세요.
    - **코드 블록(```)이나 마크다운 포맷은 절대 사용하지 마세요.**
    - **설명 없이 리스트로 문자열로 Parsing할 수 있도록 출력하세요.**
    - 출력 형식 예시: ["React", "상태 관리", "API 호출"]
    - 키워드 개수는 3개를 넘지 않아야 합니다.

    [TIL 내용]
    {content}

    키워드 리스트:
    """
        return prompt