from pydantic import BaseModel, Field
from typing import Optional

class ProxyConfig(BaseModel):
    title: str = Field(default="Proxy Server")
    worker_timeout: float = Field(default=30.0, description="Worker timeout in seconds")
    stream_timeout: float = Field(default=30.0, description="Stream timeout in seconds")
    api_key: Optional[str] = Field(default=None, description="API key for authentication (optional)")

server_config = ProxyConfig(
    api_key = None        # api key for client and worker
)