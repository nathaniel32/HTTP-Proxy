from pydantic import BaseModel, Field
from typing import Dict, Optional, Any
from enum import Enum
from datetime import datetime


class MessageType(str, Enum):
    """Types of messages exchanged between proxy and worker"""
    REQUEST = "request"
    RESPONSE_START = "response_start"
    RESPONSE_DATA = "response_data"
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


class BaseMessage(BaseModel):
    """Base class for all messages"""
    type: MessageType
    request_id: str = Field(..., description="Unique request identifier")
    
    class Config:
        use_enum_values = True


class ProxyRequest(BaseMessage):
    """Request message sent from proxy server to worker"""
    type: MessageType = Field(default=MessageType.REQUEST)
    method: HTTPMethod = Field(..., description="HTTP method")
    path: str = Field(..., description="Request path")
    headers: Dict[str, str] = Field(default_factory=dict)
    query_params: Dict[str, str] = Field(default_factory=dict)
    body: Optional[str] = Field(None, description="Request body as string")
    timestamp: str = Field(
        default_factory=lambda: datetime.utcnow().isoformat(),
        description="Request timestamp"
    )


class ResponseStart(BaseMessage):
    """Initial response message from worker to proxy"""
    type: MessageType = Field(default=MessageType.RESPONSE_START)
    status_code: int = Field(..., description="HTTP status code")
    headers: Dict[str, str] = Field(default_factory=dict)
    content_type: str = Field(default="application/json")


class ResponseData(BaseMessage):
    """Streaming response data from worker to proxy"""
    type: MessageType = Field(default=MessageType.RESPONSE_DATA)
    data: str = Field(..., description="Response data")


class ResponseEnd(BaseMessage):
    """End of response signal from worker to proxy"""
    type: MessageType = Field(default=MessageType.RESPONSE_END)


class ErrorMessage(BaseMessage):
    """Error message from worker to proxy"""
    type: MessageType = Field(default=MessageType.ERROR)
    error: str = Field(..., description="Error message")
    details: Optional[Dict[str, Any]] = Field(None, description="Additional error details")


class HealthResponse(BaseModel):
    """Health check response"""
    status: str = Field(..., description="Service status")
    workers: int = Field(..., description="Number of connected workers")
    pending_requests: int = Field(..., description="Number of pending requests")
    timestamp: str = Field(
        default_factory=lambda: datetime.utcnow().isoformat(),
        description="Health check timestamp"
    )