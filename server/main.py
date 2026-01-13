from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.responses import StreamingResponse
import asyncio
import json
import uuid
import logging
from typing import Dict
from datetime import datetime

from common.models import (
    MessageType,
    HTTPMethod,
    ProxyRequest,
    ResponseStart,
    ResponseChunk,
    ResponseEnd,
    ErrorMessage,
    HealthResponse,
    ProxyConfig
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

config = ProxyConfig()
app = FastAPI(title=config.title)

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
            message_dict = json.loads(data)
            
            # Handle response from worker
            request_id = message_dict.get("request_id")
            if request_id and request_id in pending_requests:
                await pending_requests[request_id].put(message_dict)
                    
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
    
    # Prepare request data using Pydantic model
    body = await request.body()
    proxy_req = ProxyRequest(
        request_id=request_id,
        method=HTTPMethod(request.method),
        path=f"/{path}",
        headers=dict(request.headers),
        query_params=dict(request.query_params),
        body=body.decode() if body else None
    )
    
    # Create queue for response
    queue = asyncio.Queue()
    pending_requests[request_id] = queue
    
    try:
        # Send request to worker
        await worker.send_text(proxy_req.model_dump_json())
        logger.info(f"Request {request_id} sent to worker {worker_id}: {request.method} /{path}")
        
        # Wait for start of response
        first_message = await asyncio.wait_for(queue.get(), timeout=config.worker_timeout)
        
        # Validate response type
        msg_type = first_message.get("type")
        
        if msg_type == MessageType.ERROR:
            error_msg = ErrorMessage(**first_message)
            raise HTTPException(status_code=500, detail=error_msg.error)

        if msg_type != MessageType.RESPONSE_START:
            raise HTTPException(status_code=502, detail="Invalid response from worker")
        
        # Parse response start
        response_start = ResponseStart(**first_message)
             
        async def response_stream():
            try:
                while True:
                    # Wait for next chunk
                    message = await asyncio.wait_for(queue.get(), timeout=config.stream_timeout)
                    msg_type = message.get("type")
                    
                    if msg_type == MessageType.RESPONSE_CHUNK:
                        chunk_msg = ResponseChunk(**message)
                        yield chunk_msg.chunk
                    elif msg_type == MessageType.RESPONSE_END:
                        break
                    elif msg_type == MessageType.ERROR:
                        error_msg = ErrorMessage(**message)
                        logger.error(f"Stream error for {request_id}: {error_msg.error}")
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
            status_code=response_start.status_code,
            headers=response_start.headers,
            media_type=response_start.content_type
        )
        
    except asyncio.TimeoutError:
        if request_id in pending_requests:
            del pending_requests[request_id]
        raise HTTPException(status_code=504, detail="Worker timeout")
    except HTTPException:
        if request_id in pending_requests:
            del pending_requests[request_id]
        raise
    except Exception as e:
        if request_id in pending_requests:
            del pending_requests[request_id]
        logger.error(f"Error processing request {request_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/health", response_model=HealthResponse)
async def health():
    return HealthResponse(
        status="healthy",
        workers=len(workers),
        pending_requests=len(pending_requests)
    )