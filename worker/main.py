import asyncio
import websockets
import json
import httpx
import logging
from typing import AsyncGenerator

from common.models import (
    MessageType,
    ProxyRequest,
    ResponseStart,
    ResponseChunk,
    ResponseEnd,
    ErrorMessage,
    WorkerConfig
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load configuration
config = WorkerConfig(
    target_api_host="localhost",
    target_api_port=11434,
    target_api_scheme="http",
    proxy_server_url="ws://localhost:8000/worker"
)


async def handle_request(request_data: dict) -> AsyncGenerator[dict, None]:
    """Make HTTP request to target API and yield response parts"""
    
    # Parse request using Pydantic model
    try:
        proxy_req = ProxyRequest(**request_data)
    except Exception as e:
        logger.error(f"Invalid request data: {e}")
        yield ErrorMessage(
            request_id=request_data.get("request_id", "unknown"),
            error=f"Invalid request format: {str(e)}"
        ).model_dump()
        return
    
    # Remove host header to avoid conflicts
    headers = proxy_req.headers.copy()
    headers.pop("host", None)
    
    url = f"{config.target_api_url}{proxy_req.path}"
    logger.info(f"Worker processing request {proxy_req.request_id}: {proxy_req.method} {url}")
    
    try:
        async with httpx.AsyncClient() as client:
            async with client.stream(
                method=proxy_req.method,
                url=url,
                headers=headers,
                content=proxy_req.body.encode() if proxy_req.body else None,
                timeout=config.request_timeout
            ) as response:
                
                # Send start of response
                response_start = ResponseStart(
                    request_id=proxy_req.request_id,
                    status_code=response.status_code,
                    headers=dict(response.headers),
                    content_type=response.headers.get("content-type", "application/json")
                )
                yield response_start.model_dump()
                
                # Stream content
                async for chunk in response.aiter_text():
                    chunk_msg = ResponseChunk(
                        request_id=proxy_req.request_id,
                        chunk=chunk
                    )
                    yield chunk_msg.model_dump()
                
                # Send end of response
                response_end = ResponseEnd(request_id=proxy_req.request_id)
                yield response_end.model_dump()
            
    except httpx.TimeoutException as e:
        logger.error(f"Timeout for request {proxy_req.request_id}: {e}")
        error_msg = ErrorMessage(
            request_id=proxy_req.request_id,
            error="Request timeout",
            details={"exception": str(e)}
        )
        yield error_msg.model_dump()
        
    except httpx.RequestError as e:
        logger.error(f"Request error for {proxy_req.request_id}: {e}")
        error_msg = ErrorMessage(
            request_id=proxy_req.request_id,
            error=f"Request failed: {str(e)}",
            details={"exception_type": type(e).__name__}
        )
        yield error_msg.model_dump()
        
    except Exception as e:
        logger.error(f"Unexpected error processing request {proxy_req.request_id}: {e}")
        error_msg = ErrorMessage(
            request_id=proxy_req.request_id,
            error=f"Internal error: {str(e)}",
            details={"exception_type": type(e).__name__}
        )
        yield error_msg.model_dump()


async def worker():
    """Connects to server and processes requests"""
    while True:
        try:
            async with websockets.connect(config.proxy_server_url) as websocket:
                logger.info(f"Worker connected to proxy server at {config.proxy_server_url}")
                logger.info(f"Forwarding requests to {config.target_api_url}")
                
                async for message in websocket:
                    try:
                        request_data = json.loads(message)
                        
                        if request_data.get("type") == MessageType.REQUEST:
                            # Process request and send response parts
                            async for response_part in handle_request(request_data):
                                await websocket.send(json.dumps(response_part))
                            
                            logger.info(f"Response completed for request {request_data.get('request_id')}")
                            
                    except json.JSONDecodeError as e:
                        logger.error(f"Invalid JSON message: {e}")
                    except Exception as e:
                        logger.error(f"Error handling message: {e}")
                        # Try to send error back if we have request_id
                        if "request_id" in request_data:
                            error_msg = ErrorMessage(
                                request_id=request_data["request_id"],
                                error=f"Message handling error: {str(e)}"
                            )
                            await websocket.send(error_msg.model_dump_json())
                        
        except websockets.exceptions.WebSocketException as e:
            logger.error(f"WebSocket error: {e}")
            logger.info(f"Reconnecting in {config.reconnect_delay} seconds...")
            await asyncio.sleep(config.reconnect_delay)
        except Exception as e:
            logger.error(f"Unexpected error: {e}")
            logger.info(f"Reconnecting in {config.reconnect_delay} seconds...")
            await asyncio.sleep(config.reconnect_delay)


if __name__ == "__main__":
    logger.info("Starting worker...")
    logger.info(f"Configuration: {config.model_dump()}")
    asyncio.run(worker())