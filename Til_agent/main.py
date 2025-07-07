from commit_analysis_tools import CommitTools
from agent_schema import (
    CommitDataSchema,
    InputSchema
)
from pydantic import BaseModel
from fastapi import FastAPI, Request
from confluent_kafka import Producer
from dotenv import load_dotenv
from supervisor import SupervisorGraph
import traceback
import logging
import os

get_commit_data = CommitTools.get_commit_data
load_dotenv()

app = FastAPI()

producer_conf = {
    'bootstrap.servers': '34.64.163.146:9094'
}

producer = Producer(producer_conf)

@app.post("/generate_til")
async def commit_analysis(input: InputSchema):
    try:
        commit_data = get_commit_data(owner=input.owner, repo=input.repo, branch=input.branch, sha_list=input.sha_list)
        

        input_commit = CommitDataSchema(**commit_data)
        no_files = len(input_commit.files)
        graph = await SupervisorGraph(no_files=no_files).make_supervisor_graph()
        final_result = await graph.ainvoke(input_commit)

        selected_output = {
            "final_report": final_result["final_report"],
            "source_str": final_result["source_str"],
        }

    except Exception as e:
        traceback.print_exc()
        return {"error": str(e)}

    return selected_output

class MessageRequest(BaseModel):
    message: str

@app.post("/produce")
async def produce(body: MessageRequest):
    try:
        # Kafka 메시지 전송
        producer.produce(topic="jun", value=body.message.encode("utf-8"))
        producer.flush()
        return {"status": "sent", "message": body.message}
    except Exception as e:
        logging.exception("Failed to send")
        return {"error": str(e)}