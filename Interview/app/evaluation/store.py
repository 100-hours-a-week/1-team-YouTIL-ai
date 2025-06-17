from database.db import SessionLocal
from evaluation.models import EvaluationResult

def store_to_db(data: dict):
    db = SessionLocal()
    try:
        result = EvaluationResult(**data)
        db.add(result)
        db.commit()
        db.refresh(result)
    except Exception as e:
        db.rollback()
        print(f"❌ DB 저장 실패: {e}")
    finally:
        db.close()