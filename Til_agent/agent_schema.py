import operator
from pydantic import BaseModel, Field
from typing import List, Optional, Annotated
from langgraph.graph import MessagesState

#=====================================Kafka Schema==========================================================
class MessageRequest(BaseModel):
    requestId: str
    process: Optional[str] = None
#=====================================Input Schema==========================================================
class InputSchema(BaseModel):
    owner: str = Field(description="GitHub 커밋 레포지토리 소유자")
    repo: str = Field(description="GitHub 커밋 레포지토리 이름")
    date: Optional[str] = Field(default=None, description="GitHub 커밋 레포지토리 브랜치의 커밋 날짜")
    branch: str = Field(description="GitHub 커밋 레포지토리 브랜치")
    sha_list: List[str] = Field(description="GitHub 커밋 레포지토리 브랜치의 커밋 해시 리스트")
    kafka_request: Optional[MessageRequest] = None
#=====================================Commit Analysis Schema================================================
class PatchSchema(BaseModel):
    commit_message:str = Field(description="GitHub 커밋 메시지")
    patch:str = Field(description="커밋된 코드 변경 사항")

class FileSchema(BaseModel):
    filepath:str = Field(description="커밋된 파일 이름(이렉토리 경로 포함)")
    latest_code:str = Field(description= "커밋이 반영된 최신 버전의 코드")
    node_id: Optional[int] = Field(default=None, description="커밋된 파일의 노드 아이디")
    patches:List[PatchSchema]

class CommitAnalysisSchema(BaseModel):
    filename: str = Field(description="파일 이름")
    code_review: str = Field(description="커밋 변경 내용 요약")
    code: str = Field(description = "커밋이 반영된 코드")
    code_diff: List[PatchSchema] = Field(description="커밋에 적용된 코드 조각 리스트")

class CommitDataSchema(BaseModel):
    username:str = Field(description="GitHub 유저 이름")
    repo:str = Field(description="GitHub 커밋 레포지토리 이름")
    date:str = Field(description="GitHub 커밋이 발생한 날짜")
    files: Annotated[List[FileSchema], "파일별 커밋 정보, summary 포함"]
    commit_report: Optional[str] = None
    sections: Annotated[Optional[List[CommitAnalysisSchema]], operator.add] = Field(default=None, description="커밋 분석 결과 리스트") 
    kafka_request: Optional[MessageRequest] = None

class CommitAnalysisResults(BaseModel):
    commit_analysis: Annotated[List[CommitAnalysisSchema], operator.add] = Field(
        description="커밋 분석 결과 리스트"
        )
    
class SearchQuery(BaseModel):
    search_query: str = Field(None, description="Query for web search.")
#=====================================Research Agent Team Schema==============================================
class FinishResearch(BaseModel):
    """연구를 종료합니다."""

class ReportState(MessagesState):
    section: CommitAnalysisSchema
    section_report: str = ""
    search_queries: list[SearchQuery] = []
    search_iterations: int = 3
    source_result: Annotated[str, operator.add] = None # String of formatted source content from web search

class SectionWriterInput(BaseModel):
    """Section of the report."""
    research_keywords: List[str] = Field(..., description="리서치에 사용된 키워드")
    source_result: str = Field(..., description="웹 리서치 결과 요약")

class CommitReportSchema(BaseModel):
    filename: str = Field(description="커밋 파일 이름")
    research_keywords: Annotated[List[str], operator.add] = Field(description="커밋 보고서 주요 개념 및 중요 정보")
    commit_report: str = Field(description="웹 검색 기반 커밋 보고서")

class ReportOutputState(BaseModel):
    """State of the report output."""
    completed_sections: List[CommitReportSchema] = Field(
        description="커밋 보고서 본문 내용",
    )
    source_str: Annotated[str, operator.add] = Field(
        description="The source string of the report.",
    )
#=====================================Supervisor Schema======================================================
class Sections(BaseModel):
    """Commit Analysis Schema의 각 요소를 리스트로 전달"""
    sections: Annotated[List[CommitAnalysisSchema], operator.add] = Field(
        description="보고서의 각 섹션"
    )

class Introduction(BaseModel):
    """보고서의 Introduction 작성"""
    name: str = Field(
        description="Introduction 제목",
    )
    content: str = Field(
        description="Introduction의 내용, 보고서의 개요를 제공합니다."
    )

class Conclusion(BaseModel):
    """보고서의 Conclusion 작성"""
    name: str = Field(
        description="Conclusion 제목",
    )
    content: str = Field(
        description="Conclusion의 내용, 보고서의 결론을 제공합니다."
    )

# No-op tool to indicate that the report writing is complete
class FinishReport(BaseModel):
    """보고서를 종료합니다."""

## State
class TilStateOutput(MessagesState):
    final_report: str # Final report
    # for evaluation purposes only
    # this is included only if configurable.include_source_str is True
    source_str: Annotated[str, operator.add] # String of formatted source content from web search

class TilState(MessagesState):
    sections: Annotated[list[CommitAnalysisSchema], operator.add] # List of report sections 
    completed_sections: Annotated[list[CommitReportSchema], operator.add] # Send() API key
    final_report: str # Final report
    kafka_request: MessageRequest
    # for evaluation purposes only
    # this is included only if configurable.include_source_str is True
    source_str: Annotated[str, operator.add] # String of formatted source content from web search
