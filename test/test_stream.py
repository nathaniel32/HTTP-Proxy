from fastapi import FastAPI
from fastapi.responses import StreamingResponse
import time

app = FastAPI()

def event_stream():
    for i in range(1, 20):
        yield f"data: Streaming data {i}\n\n"  # SSE format
        time.sleep(1)

@app.get("/")
def sse():
    return StreamingResponse(event_stream(), media_type="text/event-stream")
