from pydantic import BaseModel
from typing import Optional

class ProxyConfig(BaseModel):
    title: str
    worker_timeout: float
    stream_timeout: float
    api_key: Optional[str]

server_config = ProxyConfig(
    title="Proxy Server",
    worker_timeout=30.0,
    stream_timeout=30.0,
    api_key = None        # api key for client and worker
)