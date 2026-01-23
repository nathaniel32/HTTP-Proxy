import asyncio
import websockets
from websockets.client import ClientProtocol
import json
import httpx
import logging
import ssl
import certifi
import base64
from typing import AsyncGenerator
from worker.config import WorkerConfig, worker_config
from common.models import MessageType, ProxyRequest, ResponseStart, ResponseData, ResponseEnd, ErrorMessage
from common.protocol import WebSocketProtocol

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class RequestHandler:
    def __init__(self, config: WorkerConfig):
        self.config = config
    
    async def process(self, request_data: dict) -> AsyncGenerator[dict, None]:
        """Process request and yield response parts"""
        
        # Parse and validate request
        try:
            proxy_req = ProxyRequest(**request_data)
        except Exception as e:
            logger.error(f"Invalid request data: {e}")
            yield ErrorMessage(
                request_id=request_data.get("request_id", "unknown"),
                error=f"Invalid request format: {str(e)}"
            ).model_dump()
            return
        
        # Prepare request
        headers = proxy_req.headers.copy()
        headers.pop("host", None)
        
        url = f"{self.config.target_hostname}{proxy_req.path}"
        logger.info(f"Processing request {proxy_req.request_id}: {proxy_req.method} {url}")
        
        try:
            async for response_part in self._make_request(proxy_req, url, headers):
                yield response_part
                
        except Exception as e:
            logger.error(f"Unexpected error for {proxy_req.request_id}: {e}")
            yield ErrorMessage(
                request_id=proxy_req.request_id,
                error=f"Internal error: {str(e)}",
                details={"exception_type": type(e).__name__}
            ).model_dump()
    
    async def _make_request(
        self, 
        proxy_req: ProxyRequest, 
        url: str, 
        headers: dict
    ) -> AsyncGenerator[dict, None]:
        """Make HTTP request and stream response"""
        
        try:
            async with httpx.AsyncClient() as client:
                async with client.stream(
                    method=proxy_req.method,
                    url=url,
                    headers=headers,
                    content=proxy_req.body.encode() if proxy_req.body else None,
                    timeout=self.config.request_timeout
                ) as response:
                    
                    # Send response start
                    yield ResponseStart(
                        request_id=proxy_req.request_id,
                        status_code=response.status_code,
                        headers=dict(response.headers),
                        content_type=response.headers.get("content-type", "application/json")
                    ).model_dump()
                    
                    # Stream data
                    async for data in response.aiter_bytes():
                        b64_data = base64.b64encode(data).decode('utf-8')
                        yield ResponseData(
                            request_id=proxy_req.request_id,
                            data=b64_data
                        ).model_dump()
                    
                    # Send response end
                    yield ResponseEnd(
                        request_id=proxy_req.request_id
                    ).model_dump()
                    
        except httpx.TimeoutException as e:
            logger.error(f"Timeout for {proxy_req.request_id}: {e}")
            yield ErrorMessage(
                request_id=proxy_req.request_id,
                error="Request timeout",
                details={"exception": str(e)}
            ).model_dump()
            
        except httpx.RequestError as e:
            logger.error(f"Request error for {proxy_req.request_id}: {e}")
            yield ErrorMessage(
                request_id=proxy_req.request_id,
                error=f"Request failed: {str(e)}",
                details={"exception_type": type(e).__name__}
            ).model_dump()


class ProxyWorker:
    def __init__(self, config: WorkerConfig):
        self.config = config
        self.handler = RequestHandler(config)
        self.running = False
        self.ssl_context = ssl.create_default_context(cafile=certifi.where()) if config.proxy_server_url.startswith("wss://") else None
        self.protocol = WebSocketProtocol(chunk_size=config.chunk_size)
    
    async def start(self):
        self.running = True
        logger.info("Starting worker...")
        logger.info(f"Configuration: {self.config.model_dump()}")
        
        while self.running:
            try:
                await self._connect_and_process()
            except websockets.exceptions.WebSocketException as e:
                logger.error(f"WebSocket error: {e}")
                logger.info(f"Reconnecting in {self.config.reconnect_delay} seconds...")
                await asyncio.sleep(self.config.reconnect_delay)
            except Exception as e:
                logger.error(f"Unexpected error: {e}")
                logger.info(f"Reconnecting in {self.config.reconnect_delay} seconds...")
                await asyncio.sleep(self.config.reconnect_delay)
    
    async def _connect_and_process(self):
        """Connect to proxy server and process messages"""
        async with websockets.connect(self.config.proxy_server_url, ssl=self.ssl_context, additional_headers={"Authorization": f"Bearer {self.config.api_key}"}) as websocket:
            logger.info(f"Connected to proxy server at {self.config.proxy_server_url}")
            logger.info(f"Forwarding requests to {self.config.target_hostname}")
            
            while True:
                try:
                    message_dict = await self.protocol.receive_message(websocket)
                    await self._handle_message(websocket, message_dict)
                except websockets.exceptions.ConnectionClosed:
                    logger.info("Connection closed by server")
                    break
    
    async def _handle_message(self, websocket: ClientProtocol, request_data: dict):
        """Handle incoming message from proxy server"""
        try:
            if request_data.get("type") == MessageType.REQUEST:
                async for response_part in self.handler.process(request_data):
                    await self.protocol.send_message(websocket, response_part)
                
                logger.info(f"Response completed for request {request_data.get('request_id')}")
                
        except Exception as e:
            logger.error(f"Error handling message: {e}")
            # Try to send error back if we have request_id
            if "request_id" in request_data:
                error_msg = ErrorMessage(
                    request_id=request_data["request_id"],
                    error=f"Message handling error: {str(e)}"
                )
                try:
                    await self.protocol.send_message(websocket, error_msg.model_dump())
                except:
                    logger.error("Failed to send error message back")
    
    def stop(self):
        self.running = False
        logger.info("Worker stopping...")

if __name__ == "__main__":
    logging.info(f"Proxy Server: {worker_config.proxy_server_url}")
    logging.info(f"Target Hostname: {worker_config.target_hostname}")
    logging.info(f"API Key: {worker_config.api_key}")
    
    worker = ProxyWorker(worker_config)
    
    try:
        asyncio.run(worker.start())
    except KeyboardInterrupt:
        logger.info("Received keyboard interrupt")
        worker.stop()