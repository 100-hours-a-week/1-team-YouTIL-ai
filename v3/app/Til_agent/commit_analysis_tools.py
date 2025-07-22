from datetime import datetime
import os
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

class CommitTools:

    @staticmethod
    def _get_retry_session(retries=5, backoff_factor=1.0, status_forcelist=(502, 503, 504)):
        """자동 재시도 가능한 requests 세션 생성"""
        session = requests.Session()
        retry = Retry(
            total=retries,
            read=retries,
            connect=retries,
            backoff_factor=backoff_factor,
            status_forcelist=status_forcelist,
            raise_on_status=False  # 상태코드가 4xx, 5xx여도 예외를 던지지 않음
        )
        adapter = HTTPAdapter(max_retries=retry)
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        return session

    @staticmethod
    async def get_commit_data(owner: str, repo: str, sha_list: list, branch: str, github_token: str) -> dict:
        """
        GitHub에서 특정 커밋들의 변경 파일과 패치 내용을 가져오는 도구입니다.
        """
        headers = {
            "Authorization": f"Bearer {github_token}",
            "Accept": "application/vnd.github+json"
        }

        session = CommitTools._get_retry_session()

        files_by_path = {}

        for sha in sha_list:
            commit_url = f"https://api.github.com/repos/{owner}/{repo}/commits/{sha}"

            try:
                response = session.get(commit_url, headers=headers, timeout=60)
                response.raise_for_status()
            except requests.exceptions.RequestException as e:
                print(f"Error fetching commit {sha}: {e}")
                continue  # 해당 커밋 스킵

            commit_json = response.json()
            commit_message = commit_json["commit"]["message"]
            commit_date = commit_json["commit"]["committer"]["date"]

            for file in commit_json.get("files", []):
                filepath = os.path.basename(file["filename"])
                patch = file.get("patch")

                try:
                    raw_code_resp = session.get(file["raw_url"], headers=headers, timeout=60)
                    raw_code_resp.raise_for_status()
                    latest_code = raw_code_resp.text
                except requests.exceptions.RequestException as e:
                    print(f"Error fetching raw code for {filepath}: {e}")
                    latest_code = ""  # 오류 시 빈 문자열로 대체

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

        output_data = {
            "date": datetime.fromisoformat(commit_date.replace("Z", "")).strftime("%Y-%m-%d"),
            "repo": repo,
            "username": owner,
            "files": list(files_by_path.values())
        }

        return output_data