from pydantic import BaseModel, Field
from typing import List, Dict, Optional, Annotated


def merge_dicts(x: dict, y: dict) -> dict:
    if x is None:
        return y
    if y is None:
        return x
    return {**x, **y}


class PatchModel(BaseModel):
    commit_message: str
    patch: str


class FileModel(BaseModel):
    filepath: str
    latest_code: str
    patches: List[PatchModel]
    node_id: Optional[int] = None  # 추가


class TilJsonModel(BaseModel):
    username: str
    date: str
    repo: str
    title: str
    keywords: List[str]
    content: str
    vector: List[float]


class StateModel(BaseModel):
    username: str
    date: str
    repo: str
    files: List[FileModel]  # node_id가 포함된 파일 리스트

    # 선택 필드들 (초기엔 없을 수 있음)
    code_summary: Annotated[Dict[str, str], merge_dicts] = Field(default_factory=dict)
    patch_summary: Annotated[Dict[str, str], merge_dicts] = Field(default_factory=dict)
    til_draft: Optional[str] = None
    til_final: Optional[str] = None
    til_json: Optional[TilJsonModel] = None