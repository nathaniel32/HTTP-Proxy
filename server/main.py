from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.responses import StreamingResponse
import asyncio
import json
import uuid
import logging
from typing import Dict
from datetime import datetime

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Proxy Server")

workers: Dict[str, WebSocket] = {}
pending_requests: Dict[str, asyncio.Queue] = {}

@app.websocket("/worker")
async def worker_endpoint(websocket: WebSocket):
    await websocket.accept()
    worker_id = str(uuid.uuid4())
    workers[worker_id] = websocket
    logger.info(f"Worker {worker_id} connected. Total workers: {len(workers)}")
    
    try:
        while True:
            data = await websocket.receive_text()
            message = json.loads(data)
            
            # Handle response from worker
            request_id = message.get("request_id")
            if request_id and request_id in pending_requests:
                await pending_requests[request_id].put(message)
                    
    except WebSocketDisconnect:
        logger.info(f"Worker {worker_id} disconnected")
    except Exception as e:
        logger.error(f"Worker {worker_id} error: {e}")
    finally:
        del workers[worker_id]
        logger.info(f"Worker {worker_id} removed. Total workers: {len(workers)}")

@app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS", "HEAD"])
async def proxy_request(request: Request, path: str):
    """Proxy all HTTP requests to workers"""
    
    if not workers:
        raise HTTPException(status_code=503, detail="No workers available")
    
    # Get first available worker (TODO implement load balancing)
    worker_id = next(iter(workers))
    worker = workers[worker_id]
    
    # Generate unique request ID
    request_id = str(uuid.uuid4())
    
    # Prepare request data
    body = await request.body()
    request_data = {
        "type": "request",
        "request_id": request_id,
        "method": request.method,
        "path": f"/{path}",
        "headers": dict(request.headers),
        "query_params": dict(request.query_params),
        "body": body.decode() if body else None,
        "timestamp": datetime.utcnow().isoformat()
    }
    
    # Create queue for response
    queue = asyncio.Queue()
    pending_requests[request_id] = queue
    
    try:
        # Send request to worker
        await worker.send_text(json.dumps(request_data))
        logger.info(f"Request {request_id} sent to worker {worker_id}: {request.method} /{path}")
        
        # Wait for start of response
        first_message = await asyncio.wait_for(queue.get(), timeout=30.0)
        
        if first_message.get("type") == "error":
             raise HTTPException(status_code=500, detail=first_message.get("error", "Unknown error"))

        if first_message.get("type") != "response_start":
             raise HTTPException(status_code=502, detail="Invalid response from worker")
             
        async def response_stream():
            try:
                while True:
                    # Wait for next chunk
                    message = await asyncio.wait_for(queue.get(), timeout=30.0)
                    
                    if message.get("type") == "response_chunk":
                        yield message.get("chunk", "")
                    elif message.get("type") == "response_end":
                        break
                    elif message.get("type") == "error":
                        # stop streaming.
                        logger.error(f"Stream error for {request_id}: {message.get('error')}")
                        break
            except asyncio.TimeoutError:
                logger.error(f"Stream timeout for {request_id}")
            except Exception as e:
                logger.error(f"Stream error for {request_id}: {e}")
            finally:
                if request_id in pending_requests:
                    del pending_requests[request_id]

        return StreamingResponse(
            response_stream(),
            status_code=first_message.get("status_code", 200),
            headers=first_message.get("headers", {}),
            media_type=first_message.get("content_type", "application/json")
        )
        
    except asyncio.TimeoutError:
        if request_id in pending_requests:
            del pending_requests[request_id]
        raise HTTPException(status_code=504, detail="Worker timeout")
    except Exception as e:
        if request_id in pending_requests:
            del pending_requests[request_id]
        logger.error(f"Error processing request {request_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/health")
async def health():
    return {
        "status": "healthy",
        "workers": len(workers),
        "pending_requests": len(pending_requests)
    }