from typing import Optional, Dict, Any
from .agent_schema import MessageRequest
from confluent_kafka import Producer
import json
import os
import datetime
import logging

def get_config_value(value):
    """
    문자열, 받아쓰기 및 열거형 구성 값의 경우를 처리하는 함수
    """
    if isinstance(value, str):
        return value
    elif isinstance(value, dict):
        return value
    else:
        return value.value

def get_search_params(search_api: str, search_api_config: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """
    지정된 검색 API에서 허용된 매개변수만 포함하도록 search_api_config 사전을 필터링합니다.

    Args:
        search_api (str): 검색 API 식별자 (예: "exa", "tavily").
        search_api_config (Optional[Dict[str, Any]]): 검색 API에 대한 구성 사전.

    Returns:
        Dict[str, Any]: 검색 함수에 전달할 매개변수의 사전.
    """
    # Define accepted parameters for each search API
    SEARCH_API_PARAMS = {
        "exa": ["max_characters", "num_results", "include_domains", "exclude_domains", "subpages"],
        "tavily": ["max_results", "topic"],
        "perplexity": [],  # Perplexity accepts no additional parameters
        "arxiv": ["load_max_docs", "get_full_documents", "load_all_available_meta"],
        "pubmed": ["top_k_results", "email", "api_key", "doc_content_chars_max"],
        "linkup": ["depth"],
        "googlesearch": ["max_results"],
    }

    # Get the list of accepted parameters for the given search API
    accepted_params = SEARCH_API_PARAMS.get(search_api, [])

    # If no config provided, return an empty dict
    if not search_api_config:
        return {}

    # Filter the config to only include accepted parameters
    return {k: v for k, v in search_api_config.items() if k in accepted_params}

def get_today_str() -> str:
    """Get current date in a human-readable format."""
    return datetime.datetime.now().strftime("%Y.%m.%d")

def kafka_produce(message: MessageRequest, process: str):
    """
    Kafka 메시지 전송
    """
    producer_conf = {
    'bootstrap.servers': os.getenv("KAFKA_BROKER_IP")
}

    producer = Producer(producer_conf)
    message.process = process
    try:
        body_dict = message.dict()
        body_json = json.dumps(body_dict)
        producer.produce(topic=os.getenv("KAFKA_TOPIC"), key=message.requestId, value=message.process.encode("utf-8"))
        producer.flush()
        return {"status": "sent", "message": message}
    except Exception as e:
        logging.exception("Failed to send")
        return {"status": "failed", "message": message}