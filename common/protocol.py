import struct
import json
import logging
from typing import Any, Union
from fastapi import WebSocket
from websockets.client import ClientProtocol

logger = logging.getLogger(__name__)

class WebSocketProtocol:
    def __init__(self, chunk_size: int = 65536):
        self.chunk_size = chunk_size

    async def send_message(self, websocket: Union[WebSocket, ClientProtocol], message: dict):
        """Send message using binary chunking protocol"""
        # Serialize message
        try:
            json_str = json.dumps(message)
            data = json_str.encode('utf-8')
            total_size = len(data)

            # Send header (8 bytes size)
            header = struct.pack('>Q', total_size)
            if isinstance(websocket, WebSocket):
                await websocket.send_bytes(header)
            else:
                await websocket.send(header)

            # Send chunks
            for i in range(0, total_size, self.chunk_size):
                chunk = data[i:i + self.chunk_size]
                if isinstance(websocket, WebSocket):
                    await websocket.send_bytes(chunk)
                else:
                    await websocket.send(chunk)
        except Exception as e:
            logger.error(f"Error sending binary message: {e}")
            raise

    async def receive_message(self, websocket: Union[WebSocket, ClientProtocol]) -> dict:
        """Receive message using binary chunking protocol. Assumes the next message in the websocket stream is the header."""
        # Read header
        if isinstance(websocket, WebSocket):
            header = await websocket.receive_bytes()
        else:
            header = await websocket.recv()
            if isinstance(header, str):
                header = header.encode('utf-8') # bytes for binary protocol

        if len(header) != 8:
            raise ValueError(f"Invalid header size: {len(header)}")
        
        total_size = struct.unpack('>Q', header)[0]
        received_size = 0
        data_buffer = bytearray()

        while received_size < total_size:
            if isinstance(websocket, WebSocket):
                chunk = await websocket.receive_bytes()
            else:
                chunk = await websocket.recv()
                if isinstance(chunk, str):
                    chunk = chunk.encode('utf-8')
            
            data_buffer.extend(chunk)
            received_size += len(chunk)
        
        # Decode
        json_str = data_buffer.decode('utf-8')
        return json.loads(json_str)
