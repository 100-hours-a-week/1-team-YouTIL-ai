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
        filepath = file.filepath
        latest_code = file.latest_code

        prompt = f"""
    다음은 소프트웨어 프로젝트의 하나의 소스코드 파일입니다.
    주어진 코드를 분석하여 핵심 내용을 간단한 개조식 문장으로 요약해 주세요.

    요약 항목:
    - 사용 기술 스택 (언어, 프레임워크)
    - 주요 기능
    - 프로젝트 내 기능

    요약은 다음처럼 개조식으로 작성해 주세요:

    예시:
    - 언어: Python, 프레임워크: FastAPI
    - 기능: 사용자 인증 처리
    - 기능: API 서버 인증 모듈 담당

    [파일 경로]
    {filepath}

    [코드]
    {latest_code}
    """
        return prompt

    @classmethod
    def make_patch_summary_prompt(cls, code_summary: str, patch_section: str) -> str:
        """패치 요약 프롬프트를 생성합니다.
        
        Args:
            code_summary (str): 코드 요약 내용
            patch_section (str): 변경 이력 내용
            
        Returns:
            str: 생성된 프롬프트
        """
        prompt = f"""
    다음은 하나의 소스코드 파일에 대한 코드 요약과 변경 이력입니다.
    변경 이력(patch)을 바탕으로 변경 목적과 주요 수정사항을 간단한 개조식 문장으로 요약해 주세요.

    [코드 요약]
    {code_summary}

    [변경 이력]
    {patch_section}

    요약 항목:
    - 주요 변경 목적
    - 핵심 수정사항 요약
    - 변경 흐름 요약 (필요 시)

    요약은 다음처럼 개조식으로 작성해 주세요:

    예시:
    - 기능 추가: OAuth 인증 모듈 도입
    - 버그 수정: 로그인 세션 만료 문제 해결
    - 구조 개선: Controller 레이어 분리

    답변은 한국어로, 개조식 문장으로만 작성하세요.
    """
        return prompt


    # TIL 초안 생성 프롬프트

    @classmethod
    def til_draft_prompt(cls, username: str, date: str, repo: str, combined_summary: str) -> str:
        """TIL 초안 작성을 위한 프롬프트를 생성합니다.
        
        Args:
            username (str): 사용자 이름
            date (str): 작성 날짜
            repo (str): 저장소 정보
            combined_summary (str): 통합된 코드 및 변경 요약
            
        Returns:
            str: 생성된 프롬프트
        """
        prompt = f"""
    다음은 하나 이상의 소스코드 파일에 대한 분석 요약과 변경 이력 분석입니다. 이를 참고하여 마크다운 형식의 TIL을 작성해 주세요.

    [코드 + 변경 요약]
    {combined_summary}

    요구 조건:
    - 다음 형식의 JSON으로 작성:
    {{
    "user": "{username}",
    "date": "{date}",
    "repo": "{repo}",
    "title": "<{date} 포함 제목>",
    "keywords": ["<핵심 기술 키워드 1~3개>"],
    "content": "<마크다운 형식 TIL>"
    }}

    TIL 작성 시 반드시 포함할 항목 (개조식):
    1. 오늘 배운 내용
    2. 개념 정리
    3. 해당 개념이 필요한 이유
    4. 개념을 활용하는 방법
    5. 문제 해결 과정
    6. 하루 회고
    7. 전체적으로 개조식 문장 구성

    TIL 내용은 한국어로 작성하세요.
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
