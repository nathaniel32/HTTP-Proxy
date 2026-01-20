from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect, HTTPException, Header
from fastapi.responses import StreamingResponse, JSONResponse
import asyncio
import json
import uuid
import logging
from typing import List, Dict, Optional
from datetime import datetime
from server.config import ProxyConfig
from common.models import MessageType, HTTPMethod, ProxyRequest, ResponseStart, ResponseChunk, ErrorMessage, HealthResponse

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class WorkerManager:    
    def __init__(self):
        self.workers: List[WebSocket] = []
        self.pending_requests: Dict[str, asyncio.Queue] = {}
        self.index_dist_worker = 0
        self._lock = asyncio.Lock()
    
    async def add_worker(self, websocket: WebSocket):
        """Add worker with thread-safe lock"""
        async with self._lock:
            self.workers.append(websocket)
            logger.info(f"Worker connected. Total workers: {len(self.workers)}")
    
    async def remove_worker(self, websocket: WebSocket):
        """Remove worker with thread-safe lock"""
        async with self._lock:
            if websocket in self.workers:
                self.workers.remove(websocket)
                # Reset index if out of bounds
                if self.workers and self.index_dist_worker >= len(self.workers):
                    self.index_dist_worker = 0
                logger.info(f"Worker removed. Total workers: {len(self.workers)}")
    
    async def get_available_worker(self) -> WebSocket:
        """Get worker using round-robin distribution with thread-safe lock"""
        async with self._lock:
            if not self.workers:
                raise HTTPException(status_code=503, detail="No workers available")
            
            worker_count = len(self.workers)
            index = self.index_dist_worker % worker_count
            worker = self.workers[index]
            self.index_dist_worker = (index + 1) % worker_count
            
            logger.debug(f"Distributing to worker {index}/{worker_count}")
            return worker
    
    def create_request_queue(self, request_id: str, timeout: float = 60.0) -> asyncio.Queue:
        """Create queue for pending request with auto-cleanup"""
        queue = asyncio.Queue()
        self.pending_requests[request_id] = queue
        # Schedule auto-cleanup to prevent memory leak
        asyncio.create_task(self._auto_cleanup(request_id, timeout))
        return queue
    
    async def _auto_cleanup(self, request_id: str, timeout: float):
        """Auto cleanup stale requests after timeout"""
        await asyncio.sleep(timeout)
        if request_id in self.pending_requests:
            logger.warning(f"Request {request_id} timeout - auto cleaning up")
            self.cleanup_request(request_id)
    
    def cleanup_request(self, request_id: str):
        """Clean up pending request"""
        if request_id in self.pending_requests:
            del self.pending_requests[request_id]
            logger.debug(f"Cleaned up request {request_id}")
    
    async def handle_worker_message(self, message_dict: dict):
        """Handle incoming message from worker"""
        request_id = message_dict.get("request_id")
        if not request_id:
            logger.warning("Received message without request_id")
            return
            
        if request_id in self.pending_requests:
            await self.pending_requests[request_id].put(message_dict)
        else:
            logger.warning(f"Received message for unknown request_id: {request_id}")
    
    @property
    def worker_count(self) -> int:
        return len(self.workers)
    
    @property
    def pending_count(self) -> int:
        return len(self.pending_requests)


class AuthenticationError(Exception):
    """Custom exception untuk authentication errors"""
    pass

class ProxyServer:    
    def __init__(self, config: ProxyConfig):
        self.config = config
        self.app = FastAPI(title=config.title)
        self.manager = WorkerManager()
        self._setup_routes()
    
    def _setup_routes(self):
        """Setup all routes"""
        self.app.get("/health", response_model=HealthResponse)(self.health)
        self.app.websocket("/worker")(self.worker_endpoint)
        self.app.api_route(
            "/{path:path}", 
            methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS", "HEAD"]
        )(self.proxy_request)

    def _verify_api_key(self, authorization: Optional[str] = None):
        """Verify Bearer token, raise AuthenticationError if invalid"""
        # Skip if no API key configured
        if self.config.api_key is None:
            return
        
        if not authorization:
            raise AuthenticationError("Missing authorization header")
        
        if not authorization.startswith("Bearer "):
            raise AuthenticationError("Invalid authorization format. Use: Bearer <token>")
        
        token = authorization[7:]  # Remove "Bearer " prefix
        if token != self.config.api_key:
            logger.warning(f"Invalid API key attempt: {token[:8]}...")
            raise AuthenticationError("Invalid API key")
    
    async def worker_endpoint(self, websocket: WebSocket, authorization: Optional[str] = Header(None)):
        """WebSocket endpoint for worker connections"""
        try:
            self._verify_api_key(authorization)
        except AuthenticationError as e:
            await websocket.close(code=1008, reason=str(e))  # Policy Violation
            return
        
        await websocket.accept()
        await self.manager.add_worker(websocket)
        
        try:
            while True:
                data = await websocket.receive_text()
                message_dict = json.loads(data)
                await self.manager.handle_worker_message(message_dict)
                        
        except WebSocketDisconnect:
            logger.info("Worker disconnected normally")
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON from worker: {e}")
        except Exception as e:
            logger.error(f"Worker error: {e}", exc_info=True)
        finally:
            await self.manager.remove_worker(websocket)

    async def proxy_request(self, request: Request, path: str, authorization: Optional[str] = Header(None)):
        """Proxy HTTP requests to workers with streaming support"""
        
        
        try:
            self._verify_api_key(authorization)
        except AuthenticationError as e:
            return JSONResponse(
                status_code=401,
                content={"error": str(e)},
                headers={"WWW-Authenticate": "Bearer"}
            )
        
        request_id = str(uuid.uuid4())
        worker: Optional[WebSocket] = None
        
        try:
            worker = await self.manager.get_available_worker()
            
            # Prepare request
            body = await request.body()
            proxy_req = ProxyRequest(
                request_id=request_id,
                method=HTTPMethod(request.method),
                path=f"/{path}",
                headers=dict(request.headers),
                query_params=dict(request.query_params),
                body=body.decode('utf-8') if body else None
            )
            
            # Create queue with timeout buffer
            queue = self.manager.create_request_queue(
                request_id, 
                timeout=self.config.worker_timeout + 10
            )
            
            # Send to worker
            await worker.send_text(proxy_req.model_dump_json())
            logger.info(f"Request {request_id} → worker: {request.method} /{path}")
            
            # Wait for response start
            first_message = await asyncio.wait_for(
                queue.get(), 
                timeout=self.config.worker_timeout
            )
            
            msg_type = first_message.get("type")
            
            # Handle error response
            if msg_type == MessageType.ERROR:
                error_msg = ErrorMessage(**first_message)
                logger.error(f"Worker error for {request_id}: {error_msg.error}")
                raise HTTPException(status_code=500, detail=error_msg.error)
            
            # Validate response type
            if msg_type != MessageType.RESPONSE_START:
                raise HTTPException(
                    status_code=502, 
                    detail=f"Invalid response type from worker: {msg_type}"
                )
            
            response_start = ResponseStart(**first_message)
            
            # Return streaming response
            return StreamingResponse(
                self._stream_response(request_id, queue),
                status_code=response_start.status_code,
                headers=response_start.headers,
                media_type=response_start.content_type
            )
            
        except asyncio.TimeoutError:
            self.manager.cleanup_request(request_id)
            logger.error(f"Request {request_id} timeout waiting for worker")
            raise HTTPException(status_code=504, detail="Worker response timeout")
        except HTTPException:
            self.manager.cleanup_request(request_id)
            raise
        except Exception as e:
            self.manager.cleanup_request(request_id)
            logger.error(f"Error processing request {request_id}: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail="Internal proxy error")
    
    async def _stream_response(self, request_id: str, queue: asyncio.Queue):
        """Stream response chunks from worker to client"""
        try:
            while True:
                message = await asyncio.wait_for(
                    queue.get(), 
                    timeout=self.config.stream_timeout
                )
                msg_type = message.get("type")
                
                if msg_type == MessageType.RESPONSE_CHUNK:
                    chunk_msg = ResponseChunk(**message)
                    yield chunk_msg.chunk.encode('utf-8')
                    
                elif msg_type == MessageType.RESPONSE_END:
                    logger.info(f"Stream completed for {request_id}")
                    break
                    
                elif msg_type == MessageType.ERROR:
                    error_msg = ErrorMessage(**message)
                    logger.error(f"Stream error for {request_id}: {error_msg.error}")
                    break
                else:
                    logger.warning(f"Unexpected message type in stream: {msg_type}")
                    
        except asyncio.TimeoutError:
            logger.error(f"Stream timeout for {request_id}")
        except Exception as e:
            logger.error(f"Stream error for {request_id}: {e}", exc_info=True)
        finally:
            self.manager.cleanup_request(request_id)
    
    async def health(self):
        """Health check endpoint"""
        return HealthResponse(
            status="healthy" if self.manager.worker_count > 0 else "degraded",
            workers=self.manager.worker_count,
            pending_requests=self.manager.pending_count,
            timestamp=datetime.utcnow().isoformat()
        )


# Initialize server
config = ProxyConfig()
server = ProxyServer(config)
app = server.app


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080, log_level="info")