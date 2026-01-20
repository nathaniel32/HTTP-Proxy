from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.responses import StreamingResponse
import asyncio
import json
import uuid
import logging
from typing import List, Dict
from server.config import ProxyConfig
from common.models import MessageType, HTTPMethod, ProxyRequest, ResponseStart, ResponseChunk, ErrorMessage, HealthResponse


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class WorkerManager:    
    def __init__(self):
        self.workers: List[WebSocket] = []
        self.pending_requests: Dict[str, asyncio.Queue] = {}
    
    def add_worker(self, websocket: WebSocket):
        self.workers.append(websocket)
        logger.info(f"Worker {id(websocket)} connected. Total workers: {len(self.workers)}")
    
    def remove_worker(self, websocket: WebSocket):
        if websocket in self.workers:
            self.workers.remove(websocket)
            logger.info(f"Worker {id(websocket)} removed. Total workers: {len(self.workers)}")
    
    def get_available_worker(self) -> WebSocket:
        """Get first available worker (TODO: implement load balancing)"""
        if not self.workers:
            raise HTTPException(status_code=503, detail="No workers available")
        return self.workers[0]
    
    def create_request_queue(self, request_id: str) -> asyncio.Queue:
        """Create queue for pending request"""
        queue = asyncio.Queue()
        self.pending_requests[request_id] = queue
        return queue
    
    def cleanup_request(self, request_id: str):
        """Clean up pending request"""
        if request_id in self.pending_requests:
            del self.pending_requests[request_id]
    
    async def handle_worker_message(self, message_dict: dict):
        """Handle incoming message from worker"""
        request_id = message_dict.get("request_id")
        if request_id and request_id in self.pending_requests:
            await self.pending_requests[request_id].put(message_dict)
    
    @property
    def worker_count(self) -> int:
        return len(self.workers)
    
    @property
    def pending_count(self) -> int:
        return len(self.pending_requests)


class ProxyServer:    
    def __init__(self, config: ProxyConfig):
        self.config = config
        self.app = FastAPI(title=config.title)
        self.manager = WorkerManager()
        self._setup_routes()
    
    def _setup_routes(self):
        self.app.get("/health", response_model=HealthResponse)(self.health)
        self.app.websocket("/worker")(self.worker_endpoint)
        self.app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS", "HEAD"])(self.proxy_request)
    
    async def worker_endpoint(self, websocket: WebSocket):
        await websocket.accept()
        self.manager.add_worker(websocket)
        
        try:
            while True:
                data = await websocket.receive_text()
                message_dict = json.loads(data)
                await self.manager.handle_worker_message(message_dict)
                        
        except WebSocketDisconnect:
            logger.info(f"Worker {id(websocket)} disconnected")
        except Exception as e:
            logger.error(f"Worker {id(websocket)} error: {e}")
        finally:
            self.manager.remove_worker(websocket)
    
    async def proxy_request(self, request: Request, path: str):
        """Proxy HTTP requests to workers"""
        
        worker = self.manager.get_available_worker()
        request_id = str(uuid.uuid4())
        
        # Prepare request
        body = await request.body()
        proxy_req = ProxyRequest(
            request_id=request_id,
            method=HTTPMethod(request.method),
            path=f"/{path}",
            headers=dict(request.headers),
            query_params=dict(request.query_params),
            body=body.decode() if body else None
        )
        
        queue = self.manager.create_request_queue(request_id)
        
        try:
            # Send to worker
            await worker.send_text(proxy_req.model_dump_json())
            logger.info(f"Request {request_id} sent to worker {id(worker)}: {request.method} /{path}")
            
            # Wait for response start
            first_message = await asyncio.wait_for(
                queue.get(), 
                timeout=self.config.worker_timeout
            )
            
            msg_type = first_message.get("type")
            
            if msg_type == MessageType.ERROR:
                error_msg = ErrorMessage(**first_message)
                raise HTTPException(status_code=500, detail=error_msg.error)
            
            if msg_type != MessageType.RESPONSE_START:
                raise HTTPException(status_code=502, detail="Invalid response from worker")
            
            response_start = ResponseStart(**first_message)
            
            return StreamingResponse(
                self._stream_response(request_id, queue),
                status_code=response_start.status_code,
                headers=response_start.headers,
                media_type=response_start.content_type
            )
            
        except asyncio.TimeoutError:
            self.manager.cleanup_request(request_id)
            raise HTTPException(status_code=504, detail="Worker timeout")
        except HTTPException:
            self.manager.cleanup_request(request_id)
            raise
        except Exception as e:
            self.manager.cleanup_request(request_id)
            logger.error(f"Error processing request {request_id}: {e}")
            raise HTTPException(status_code=500, detail=str(e))
    
    async def _stream_response(self, request_id: str, queue: asyncio.Queue):
        try:
            while True:
                message = await asyncio.wait_for(
                    queue.get(), 
                    timeout=self.config.stream_timeout
                )
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
            self.manager.cleanup_request(request_id)
    
    async def health(self):
        return HealthResponse(
            status="healthy",
            workers=self.manager.worker_count,
            pending_requests=self.manager.pending_count
        )


config = ProxyConfig()
server = ProxyServer(config)
app = server.app


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)