from typing_extensions import TypedDict 
from pydantic import BaseModel
from typing import List, Annotated, Dict

# 커스텀 병합 리듀서
def merge_dicts(x: dict, y: dict) -> dict:
    if x is None:
        return y
    if y is None:
        return x
    return {**x, **y}

class PatchDict(TypedDict):
    commit_message: str
    patch: str

class FileDict(TypedDict):
    filepath: str
    latest_code: str
    patches: List[PatchDict]

class TilJson(BaseModel):
    username: str
    date: str
    repo: str
    keywords: List[str]
    content: str
    vector: List[float]

class StateType(TypedDict, total=False):
    username: str
    date: str
    repo: str
    files: List[FileDict]
    code_summary: Annotated[Dict[str, str], merge_dicts]  
    patch_summary: Annotated[Dict[str, str], merge_dicts]  
    til_draft: str  # 초안
    til_final: str  # 개선된 최종 결과
    til_json: TilJson