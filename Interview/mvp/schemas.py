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

    content: Optional[List[ContentState]] = None
    summary: Optional[str] = None