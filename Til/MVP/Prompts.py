from state_types import *

class LanggraphPrompts:    
    @classmethod
    def make_code_summary_prompt(cls, file: FileModel) -> str:
        """코드 요약 프롬프트를 생성합니다.
        
        Args:
            file (dict[str, str]): 파일 정보를 담은 딕셔너리
                - filepath: 파일 경로
                - latest_code: 최신 코드 내용
                
        Returns:
            str: 생성된 프롬프트
        """
        latest_code = file.latest_code


        prompt = f"""
        다음은 소스코드입니다. 코드를 보고 핵심 내용을 **개조식 문장**으로 요약해 주세요.

        요약 항목:
        - 사용 기술 스택: 언어 및 라이브러리만 간단히
        - 주요 기능: 한 줄씩 나열 (무엇을 하는 함수인지만)
        - 프로젝트 내 역할: 전체 시스템에서 이 파일이 담당하는 기능

        ⚠️ 출력 조건:
        - 각 항목은 반드시 `-`로 시작하는 개조식 문장으로 작성하세요.
        - 서술형 문장이나 설명식 요약은 절대 작성하지 마세요.
        - 최대한 간결하게 핵심만 요약해 주세요.

        [코드]
        {latest_code}
        """
        return prompt

    @classmethod
    def make_patch_summary_prompt(cls, code_summary: str, commit_message: str, before_code: str, after_code: str) -> str:
        prompt = f"""
        다음은 한 소스코드 파일에 대한 변경 요약입니다.

        - 최근 커밋 메시지: {commit_message}

        [최신 코드 요약]
        {code_summary}

        [삭제된 코드 내용]
        {before_code}

        [추가된 코드 내용]
        {after_code}

        요구사항:
        - 아래 항목을 **개조식 문장**으로 자연스럽게 요약하세요.
            - 변경 목적
            - 어떤 기능이 제거되었고, 어떤 기능이 새로 도입되었는지
            - 이 변경이 전체 기능 또는 사용자 인터페이스에 어떤 영향을 주는지
        - ⚠️ 코드 형식이나 코드 블록(예: \`\`\` 등)은 절대 포함하지 마세요.
        - 출력은 일반 텍스트로, 마크다운이나 HTML, 코드 스타일 없이 작성하세요.
        - 중복된 문장, 불필요한 반복을 피하고 요점을 간결히 정리하세요.

        출력 예시:
        - API 응답 오류 처리 로직 추가
        - 기존 `print` 문 제거
        - 사용자 입력값 검증 로직 도입
        """
        return prompt

    # TIL 초안 생성 프롬프트

    @classmethod
    def til_draft_prompt(
        cls,
        username: str,
        date: str,
        repo: str,
        patch_summary: List[PatchSummaryModel]  # ✅ 타입 일치
    ) -> str:
        summary_blocks = []
        for item in patch_summary:
            block = f"""[파일 경로] {item.filepath}
        - 변경 목적: {item.change_purpose}
        - 주요 수정사항:
        {item.code_changes.strip()}
        """
        summary_blocks.append(block.strip())

        combined_summary = "\n\n".join(summary_blocks)

        prompt = f"""
        다음은 하나 이상의 소스코드 파일에 대한 분석 요약과 변경 이력 분석입니다. 이를 참고하여 마크다운 형식의 TIL을 작성해 주세요.
        
        [코드 + 변경 요약]
        {combined_summary}

        요구 조건:
        - 반드시 마크다운 형식으로 출력하세요. 설명, 분석, 감상은 포함하지 마세요.
        - TIL 내용은 한국어로 작성하세요.

       TIL 작성 시 반드시 포함할 항목 (개조식):
        1. 오늘 배운 내용
        2. 개념 정리
        3. 해당 개념이 필요한 이유
        4. 개념을 활용하는 방법
        5. 문제 해결 과정
        6. 하루 회고
        """

        return prompt
    
    @classmethod
    def til_title_prompt(cls, content: str) -> str:
        prompt = f"""
            다음은 한 사용자가 작성한 TIL(Today I Learned)입니다.  
            이 내용을 바탕으로 **핵심 주제를 담은 한 문장의 제목**을 작성해 주세요.

            요구 조건:
            - 1문장으로 요약된 제목을 작성하세요.
            - 핵심 기술 개념, 문제 해결 주제, 또는 학습 내용을 반영하세요.
            - 날짜나 작성자 이름은 포함하지 마세요.
            - 너무 일반적인 제목(예: "오늘 배운 것")은 피하세요.

            [TIL 내용]
            {content}
            """
        return prompt

    @classmethod
    def til_title_prompt(cls, content: str) -> str:
        prompt = f"""
        다음은 한 사용자가 작성한 TIL(Today I Learned)입니다.

        이 내용을 바탕으로 **기술적인 핵심 주제를 담은 블로그 글 스타일의 제목**을 작성해 주세요.

        요구 조건:
        - 반드시 **한 줄짜리 제목만 출력**하세요.
        - 절대로 '답변:', '제목:', '---', '###', 따옴표, 마크다운 기호(**, *, `) 등을 포함하지 마세요.
        - 문장 끝은 '~다'처럼 끝나지 않도록 하세요. **명사구나 간결한 기술 용어 조합으로 끝나야 합니다.**
        - 예시:
        - React에서 상태 관리 방식 실습
        - Kakao Maps를 활용한 위치 기반 마커 표시 기능 구현
        - Axios 에러 처리 방식 개선과 UI 반영

        [TIL 내용]
        {content}
        """.strip()
        return prompt
    
    @classmethod
    def til_keywords_prompt(cls, content: str) -> str:
        prompt = f"""
    다음 TIL 내용을 바탕으로 **핵심 키워드 1~3개**를 추출해 주세요.

    요구 조건:
    - 일반적인 단어("공부", "내용", "코드")는 제외하고, 기술적이거나 도메인 관련 키워드만 포함하세요.
    - **코드 블록(```)이나 마크다운 포맷은 절대 사용하지 마세요.**
    - **설명 없이 리스트로 문자열로 Parsing할 수 있도록 출력하세요.**
    - 출력 형식 예시: ["React", "상태 관리", "API 호출"]

    [TIL 내용]
    {content}
    """
        return prompt


    # 피드백 루프
    @classmethod
    def til_feedback_prompt(cls, content: str) -> str:
        """TIL 초안을 받아서 개선 지침을 포함한 feedback prompt를 생성합니다.

        Args:
            content (str): 초안 TIL 내용 (마크다운 텍스트)

        Returns:
            str: LLM에게 전달할 최종 프롬프트 텍스트
        """
        feedback_prompt = f"""
    다음은 오늘 학습한 내용을 정리한 TIL 초안입니다.

    [TIL 초안]
    {content}

    이 TIL을 다음 기준에 따라 평가하고, 더 구체적이고 일관성 있는 TIL로 개선해 주세요:

    ✅ 개선 기준:
    1. **중복 문장 제거** – 유사하거나 반복되는 문장은 하나로 합쳐 주세요.
    2. **표현의 명확성** – 불분명하거나 모호한 표현을 구체적으로 바꿔 주세요.
    3. **개조식 통일** – 문장형 서술이 있다면 개조식으로 정리해 주세요.
    4. **불필요한 서론 제거** – 지나치게 일반적이거나 반복되는 내용은 생략해 주세요.
    5. **자주 사용되는 추상 표현 제거** – "새로운 면모", "실감나게", "꾸준히", "흥미로웠다" 등의 모호한 감정/상태 표현은 구체적인 행동, 성과, 계획으로 바꿔 주세요.
    6. **자연스러운 문장 구성** – 한국어 맞춤법 및 어투를 자연스럽게 다듬어 주세요. 문장이 너무 길어지면 줄바꿈으로 구조를 직관적으로 보이게 작성하세요.

    ✅ 출력 형식:
    - 수정된 TIL 전체 (마크다운 형식 유지)

    **주의**: 결과는 반드시 한국어로 작성해 주세요. 초안에 대한 피드백 부분은 작성하지 마세요. **TIL 본문만 필요합니다.**
    """
        return feedback_prompt
