from datetime import datetime
import os
import requests
from dotenv import load_dotenv

load_dotenv()

github_token = os.getenv("GITHUB_ACCESS_TOKEN")

class CommitTools:
    def get_commit_data(owner:str, repo:str, sha_list:list, branch: str, github_token: str) -> dict:
        """
    GitHub에서 특정 커밋들의 변경 파일과 패치 내용을 가져오는 도구입니다.

    사용 목적:
    - 주어진 GitHub 저장소에서 여러 커밋 SHA에 해당하는 변경 내용을 분석합니다.
    - 각 커밋의 메시지와 수정된 파일 목록, 각 파일의 변경 전 코드와 patch 적용 내용을 제공합니다.
    - 에이전트는 이 정보를 활용해 코드 변경 요약, TIL 생성, 또는 리뷰 작업에 사용할 수 있습니다.

    Arguments:
    - owner: 저장소의 소유자 GitHub 사용자명
    - repo: 저장소 이름
    - date: 커밋 일자
    - branch: 커밋 브랜치 이름
    - sha_list: 커밋 SHA 문자열의 리스트
    - github_token: GitHub Personal Access Token (API 인증을 위해 필요)

    Returns:
    - 각 커밋별로 다음 정보를 담은 딕셔너리:
        - commit_message: 커밋 메시지
        - patched_code_list: 각 파일에 대해:
            - filename: 파일 이름
            - status: 변경 상태 (added, modified, removed 등)
            - patched_code: patch가 적용된 최신 코드
        """

        headers = {'Authorization':  f"Bearer {github_token}"}
        input_files = {
            'username':owner, 
            'repo': repo,  
            "branch": branch
                }
        files_by_path = {}  # filepath 기준 정리

        for i, sha in enumerate(sha_list):
            commit_url = f"https://api.github.com/repos/{owner}/{repo}/commits/{sha}"
            response = requests.get(commit_url, headers=headers, timeout=30)
            response.raise_for_status()
            response = response.json()

            commit_message = response["commit"]["message"]
            commit_date = response["commit"]["committer"]["date"]
            
            for file in response["files"]:
                filepath = os.path.basename(file["filename"])
                patch = file.get("patch")
                latest_code = requests.get(file["raw_url"]).text

                # 파일 기준으로 정리
                if filepath not in files_by_path:
                    files_by_path[filepath] = {
                        "filepath": filepath,
                        "latest_code": latest_code,
                        "patches": []
                    }

                files_by_path[filepath]["patches"].append({
                    "patch": patch,
                    "commit_message": commit_message
                })

        # 최종 정리된 형태
        output_data = {
            "date": datetime.fromisoformat(commit_date.replace("Z", "")).strftime("%Y-%m-%d"),  # 가장 마지막 커밋 기준
            "repo": repo,
            "username": owner,
            "files": list(files_by_path.values())
        }

        return output_data