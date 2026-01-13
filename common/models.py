from pydantic import BaseModel, Field
from typing import Dict, Optional, Any
from enum import Enum
from datetime import datetime

class MessageType(str, Enum):
    """Types of messages exchanged between proxy and worker"""
    REQUEST = "request"
    RESPONSE_START = "response_start"
    RESPONSE_CHUNK = "response_chunk"
    RESPONSE_END = "response_end"
    ERROR = "error"

class HTTPMethod(str, Enum):
    """Supported HTTP methods"""
    GET = "GET"
    POST = "POST"
    PUT = "PUT"
    DELETE = "DELETE"
    PATCH = "PATCH"
    OPTIONS = "OPTIONS"
    HEAD = "HEAD"

class ProxyRequest(BaseModel):
    """Request message sent from proxy server to worker"""
    type: MessageType = Field(default=MessageType.REQUEST)
    request_id: str = Field(..., description="Unique request identifier")
    method: HTTPMethod = Field(..., description="HTTP method")
    path: str = Field(..., description="Request path")
    headers: Dict[str, str] = Field(default_factory=dict)
    query_params: Dict[str, str] = Field(default_factory=dict)
    body: Optional[str] = Field(None, description="Request body as string")
    timestamp: str = Field(
        default_factory=lambda: datetime.utcnow().isoformat(),
        description="Request timestamp"
    )

    class Config:
        use_enum_values = True

class ResponseStart(BaseModel):
    """Initial response message from worker to proxy"""
    type: MessageType = Field(default=MessageType.RESPONSE_START)
    request_id: str = Field(..., description="Corresponding request ID")
    status_code: int = Field(..., description="HTTP status code")
    headers: Dict[str, str] = Field(default_factory=dict)
    content_type: str = Field(default="application/json")

    class Config:
        use_enum_values = True

class ResponseChunk(BaseModel):
    """Streaming response chunk from worker to proxy"""
    type: MessageType = Field(default=MessageType.RESPONSE_CHUNK)
    request_id: str = Field(..., description="Corresponding request ID")
    chunk: str = Field(..., description="Response chunk data")

    class Config:
        use_enum_values = True

class ResponseEnd(BaseModel):
    """End of response signal from worker to proxy"""
    type: MessageType = Field(default=MessageType.RESPONSE_END)
    request_id: str = Field(..., description="Corresponding request ID")

    class Config:
        use_enum_values = True

class ErrorMessage(BaseModel):
    """Error message from worker to proxy"""
    type: MessageType = Field(default=MessageType.ERROR)
    request_id: str = Field(..., description="Corresponding request ID")
    error: str = Field(..., description="Error message")
    details: Optional[Dict[str, Any]] = Field(None, description="Additional error details")

    class Config:
        use_enum_values = True

class HealthResponse(BaseModel):
    """Health check response"""
    status: str = Field(..., description="Service status")
    workers: int = Field(..., description="Number of connected workers")
    pending_requests: int = Field(..., description="Number of pending requests")
    timestamp: str = Field(
        default_factory=lambda: datetime.utcnow().isoformat(),
        description="Health check timestamp"
    )