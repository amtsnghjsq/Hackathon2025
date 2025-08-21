import json
import uuid
from datetime import datetime
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, asdict


@dataclass
class AgentMessage:
    sender_id: str
    recipient_id: str
    message_type: str
    content: Dict[str, Any]
    timestamp: str = None
    message_id: str = None
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.utcnow().isoformat()
        if self.message_id is None:
            self.message_id = str(uuid.uuid4())
    
    def to_json(self) -> str:
        return json.dumps(asdict(self))
    
    @classmethod
    def from_json(cls, json_str: str) -> 'AgentMessage':
        data = json.loads(json_str)
        return cls(**data)


@dataclass
class TaskRequest:
    task_id: str
    description: str
    parameters: Dict[str, Any]
    requester_id: str
    target_capability: str = None
    priority: str = "normal"
    
    def __post_init__(self):
        if not self.task_id:
            self.task_id = str(uuid.uuid4())


@dataclass
class TaskResponse:
    task_id: str
    status: str
    result: Any = None
    error: str = None
    agent_id: str = None
    
    def to_message(self, recipient_id: str) -> AgentMessage:
        return AgentMessage(
            sender_id=self.agent_id,
            recipient_id=recipient_id,
            message_type="task_response",
            content=asdict(self)
        )


@dataclass
class AgentCard:
    agent_id: str
    name: str
    description: str
    capabilities: List[str]
    agent_type: str
    version: str = "1.0.0"
    status: str = "active"
    
    def to_json(self) -> str:
        return json.dumps(asdict(self))
    
    @classmethod
    def from_json(cls, json_str: str) -> 'AgentCard':
        data = json.loads(json_str)
        return cls(**data)


class A2AProtocol:
    def __init__(self, agent_id: str):
        self.agent_id = agent_id
        self.message_handlers = {}
    
    def register_handler(self, message_type: str, handler):
        self.message_handlers[message_type] = handler
    
    async def send_message(self, message: AgentMessage) -> bool:
        try:
            return True
        except Exception:
            return False
    
    async def handle_message(self, message: AgentMessage) -> Optional[AgentMessage]:
        handler = self.message_handlers.get(message.message_type)
        if handler:
            return await handler(message)
        return None
    
    def create_task_request(self, description: str, parameters: Dict[str, Any], 
                          target_capability: str = None) -> TaskRequest:
        return TaskRequest(
            task_id=str(uuid.uuid4()),
            description=description,
            parameters=parameters,
            requester_id=self.agent_id,
            target_capability=target_capability
        )
    
    def create_response_message(self, recipient_id: str, content: Dict[str, Any]) -> AgentMessage:
        return AgentMessage(
            sender_id=self.agent_id,
            recipient_id=recipient_id,
            message_type="response",
            content=content
        )
