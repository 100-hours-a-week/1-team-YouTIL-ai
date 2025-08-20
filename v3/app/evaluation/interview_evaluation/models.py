from sqlalchemy import Column, Integer, Float, Text, TIMESTAMP, func, text
from app.database.db import Base

class EvaluationResult(Base):
    __tablename__ = "interview_evaluation"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    til_content = Column(Text)
    email = Column(Text)
    question = Column(Text)
    answer = Column(Text)
    summary = Column(Text)

    til_relevance_score = Column(Float)
    til_relevance_explanation = Column(Text)
    
    factual_accuracy_score = Column(Float)
    factual_accuracy_explanation = Column(Text)

    retrieval_grounding_score = Column(Float)
    retrieval_grounding_explanation = Column(Text)

    answer_quality_score = Column(Float)
    answer_quality_explanation = Column(Text)

    difficulty_fit_score = Column(Float)
    difficulty_fit_explanation = Column(Text)

    total_score = Column(Float)
    overall_evaluation = Column(Text)
    improvement_suggestions = Column(Text)
    created_at = Column(TIMESTAMP, server_default=func.now())
