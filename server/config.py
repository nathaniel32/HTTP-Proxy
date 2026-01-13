from pydantic import BaseModel, Field

class ProxyConfig(BaseModel):
    """Proxy server configuration"""
    title: str = Field(default="Proxy Server")
    worker_timeout: float = Field(default=30.0, description="Worker timeout in seconds")
    stream_timeout: float = Field(default=30.0, description="Stream timeout in seconds")