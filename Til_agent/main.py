from commit_analysis_tools import CommitTools
from agent_schema import (
    CommitDataSchema,
    InputSchema
)
from utils import kafka_produce
from pydantic import BaseModel
from fastapi import FastAPI, Request
from confluent_kafka import Producer
from dotenv import load_dotenv
from supervisor import SupervisorGraph
from agent_schema import (
    MessageRequest,
    InputSchema
)
import traceback
import logging
import os
import json

get_commit_data = CommitTools.get_commit_data
load_dotenv()

app = FastAPI()

@app.post("/generate_til")
async def commit_analysis(state: InputSchema):
    try:
        commit_data = get_commit_data(
            owner=state.owner, 
            repo=state.repo, 
            branch=state.branch, 
            sha_list=state.sha_list
        )
        
        if state.kafka_request is not None:
            kafka_produce(
                message=state.kafka_request, 
                process="GET_COMMIT_DATA_FROM_GITHUB"
            )

        input_commit = CommitDataSchema(**commit_data)
        no_files = len(input_commit.files)

        if state.kafka_request is not None:
            kafka_produce(
                message=state.kafka_request, 
                process="COMMIT_ANALYSIS_START"
            )   
        
        graph = await SupervisorGraph(no_files=no_files).make_supervisor_graph()

        input_commit.kafka_request = state.kafka_request
        final_result = await graph.ainvoke(input_commit)

        selected_output = {
            "final_report": final_result["final_report"],
            "source_str": final_result["source_str"],
        }

    except Exception as e:
        traceback.print_exc()
        return {"error": str(e)}

    return selected_output



@app.post("/produce")
async def produce(body: MessageRequest):
    try:
        # Kafka 메시지 전송
        body_dict = body.message.dict()
        body_json = json.dumps(body_dict)
        producer.produce(topic="ai.til.process", key=body.requestId, value=body_json.encode("utf-8"))
        producer.flush()
        return {"status": "sent", "message": body.message}
    except Exception as e:
        logging.exception("Failed to send")
        return {"error": str(e)}