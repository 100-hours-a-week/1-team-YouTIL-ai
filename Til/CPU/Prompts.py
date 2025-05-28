class LanggraphPrompts:
    @classmethod
    def make_til_draft(
        cls,
        final,
        ) -> str:
        
        return f"""
    The following is the commit history and code content of a single source code file. Based on this, please summarize the key information needed to write a TIL (Today I Learned) entry.

    [Input Information]
    - Commit message: {final["code_changes"][0]["commit_message"]}
    - Previous code: {final["code_changes"][0]["before_code"]}
    - Modified code: {final["code_changes"][0]["after_code"]}
    - Current code: {final["latest_code"]}

    ---

    Please summarize the following items:

    1. Purpose of change: Briefly explain why the change was made  
    2. Summary of code changes: Summarize the removed/added functionality  
    3. Tech stack used: Languages and libraries used  
    4. Key functionalities: List the main functions in one line each  
    5. Role in the project: Describe the function of this file in the overall system

    **Instructions:**
    - Include the number and title for each item.
    - Write each item clearly without indentation.
    - Do not use markdown, code blocks, or any special characters.
    - **Write your response in English.**

    Now, please complete the following format:
    """
        
    @classmethod
    def make_final_til_prompt(cls, date: str, combined_content: str) -> str:
        return f"""
    The following is a draft TIL (Today I Learned) entry created from one or more source code files. Please integrate the contents to generate a structured and comprehensive TIL markdown document summarizing what was learned during the day.

    [Date]
    {date}

    [Input Drafts]
    {combined_content}

    ⚠️ Output Rules:
    - Do not start any line with indentation.
    - Use `#` and `###` for headers, and place them at the beginning of the line without any preceding spaces.
    - Body text must also start at the beginning of the line without extra spaces or tabs.
    - The output **must be written in English only**.

    The TIL must include the following sections (in bullet-point style):

    # 📅 {date} TIL

    ### 📖 What I Learned Today

    ### 📚 Concept Summary

    ### 🤔 Why This Concept Matters

    ### 💡 How to Apply This Concept

    ### 🛠️ Problem-Solving Process

    ### ✍️ Daily Reflection

    - Write all sections in the given order without skipping.
    - Do not include any content outside these sections.
    - Use concise and clear sentences without indentation.
    - **For `Daily Reflection`, avoid subjective expressions like “It was helpful” or “I enjoyed it.” Instead, describe the tasks performed and the outcomes objectively, using a neutral and technical tone.**
    - The output **must be in English only**.

    Final TIL:
    """

    
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
    
    @classmethod
    def til_translate_prompt(cls, date:str, content: str) -> str:
        return f"""
        다음은 영어로 작성된 TIL(Today I Learned)입니다.

        [TIL]
        {content}

        - 영어로 작성된 내용을 한국어로 **그대로 번역만 해주세요.**
        - **형식(마크다운 구조)은 그대로 유지**하세요.
        - 문장을 새로 만들거나 내용을 요약하거나 재작성하지 마세요.
        - **객관적이고 보고서에 적합한 말투로 번역**해 주세요.
        - 특히 `✍️ 회고` 항목은 감정을 배제하고 **기술적인 내용 그대로** 번역해 주세요.

        **출력은 다음 마크다운 형식을 그대로 따르세요**
        # 📅 {date} TIL

        ## 📖 오늘 배운 내용

        ## 📚 개념 정리

        ## 🤔 해당 개념이 필요한 이유

        ### 💡 개념을 활용하는 방법

        ## 🛠️ 문제 해결 과정

        ## ✍️ 회고

        번역 결과:
        """
