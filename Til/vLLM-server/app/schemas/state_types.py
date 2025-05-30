from pydantic import BaseModel, Field
from typing import List, Dict, Optional, Annotated, Union
from enum import Enum


def merge_dicts(x: dict, y: dict) -> dict:
    if x is None:
        return y
    if y is None:
        return x
    return {**x, **y}

def merge_patch_summary_lists(x: list, y: list) -> list:
    if x is None:
        return y
    if y is None:
        return x
    return x + y

class keywords(str, Enum):
    keyword1 = "keyword1"
    keyword2 = "keyword2"
    keyword3 = "keyword3"
    keyword4 = "keyword4"
    keyword5 = "keyword5"
    keyword6 = "keyword6"
    keyword7 = "keyword7"
    keyword8 = "keyword8"
    keyword9 = "keyword9"
    keyword10 = "keyword10"


class TILKeywordsModel(BaseModel):
    keywords_list: List[str] = []


class PatchModel(BaseModel):
    commit_message: str
    patch: str


class FileModel(BaseModel):
    filepath: str
    latest_code: str
    patches: List[PatchModel]
    node_id: Optional[int] = None 

class PatchSummaryModel(BaseModel):
    filepath: str
    change_purpose: str
    code_changes: str  


class TilJsonModel(BaseModel):
    username: str
    date: str
    repo: str
    keywords: TILKeywordsModel
    content: str
    vector: List[float]

class StateModel(BaseModel):
    username: str
    date: str
    repo: str
    files: List[FileModel]  # node_id가 포함된 파일 리스트

    # 선택 필드들 (초기엔 없을 수 있음)
    code_summary: Annotated[Dict[str, str], merge_dicts] = Field(default_factory=dict)
    # patch_summary: Annotated[Dict[str, str], merge_dicts] = Field(default_factory=dict)
    patch_summary: Annotated[List[PatchSummaryModel], merge_patch_summary_lists] = Field(default_factory=list)
    til_draft: Optional[str] = None
    til_final: Optional[str] = None
    til_json: Optional[TilJsonModel] = None