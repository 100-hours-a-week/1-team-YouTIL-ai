from sqlalchemy import Column, Integer, Float, Text, TIMESTAMP, func
from app.database.db import Base

class EvaluationResult(Base):
    __tablename__ = "evaluation_results"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    til_content = Column(Text)
    email = Column(Text)
    question = Column(Text)
    answer = Column(Text)
    bleu_score = Column(Float)
    rouge_score = Column(Float)
    bert_score = Column(Float)
    recall_at_k = Column(Float)
    similarity_score = Column(Float)
    created_at = Column(TIMESTAMP, server_default=func.now())
