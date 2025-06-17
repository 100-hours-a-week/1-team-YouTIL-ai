from pydantic import BaseModel
from typing import List, Optional

class ContentState(BaseModel):
    question: str
    answer: str 

class QAState(BaseModel):
    email: str
    level: int
    title: str
    keywords: List[str]
    til: str
    category: str

    question0: Optional[str] = None
    question1: Optional[str] = None
    question2: Optional[str] = None

    retrieved_texts0: Optional[List[str]] = None
    retrieved_texts1: Optional[List[str]] = None
    retrieved_texts2: Optional[List[str]] = None

    similarity_score0: Optional[float] = None
    similarity_score1: Optional[float] = None
    similarity_score2: Optional[float] = None

    content0: Optional[ContentState] = None
    content1: Optional[ContentState] = None
    content2: Optional[ContentState] = None

    question: Optional[str] = None
    answer: Optional[str] = None

    content: Optional[List[ContentState]] = None
    summary: Optional[str] = None