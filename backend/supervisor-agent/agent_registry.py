import yaml
import os
from typing import Dict, List, Optional, Any
from a2a_protocol import AgentCard


class AgentRegistry:
    def __init__(self, config_file: str = "agents.yaml"):
        self.config_file = config_file
        self.agents = {}
        self.routing_rules = []
        self.default_agent = None
        self.supervisor_config = {}
        self.load_config()
    
    def load_config(self):
        if not os.path.exists(self.config_file):
            self.agents = {}
            self.routing_rules = []
            return
        
        try:
            with open(self.config_file, 'r') as f:
                config = yaml.safe_load(f)
            
            self.agents = config.get('agents', {})
            self.routing_rules = config.get('routing_rules', [])
            self.default_agent = config.get('default_agent', 'github-agent')
            self.supervisor_config = config.get('supervisor_config', {})
            
        except Exception as e:
            print(f"Error loading config: {e}")
            self.agents = {}
            self.routing_rules = []
    
    def get_agent_config(self, agent_key: str) -> Optional[Dict]:
        if agent_key in self.agents:
            return self.agents[agent_key]
        
        for key, config in self.agents.items():
            if config.get('id') == agent_key:
                return config
        return None
    
    def find_agents_by_capability(self, capability: str) -> List[str]:
        matching_agents = []
        for agent_key, agent_config in self.agents.items():
            if capability in agent_config.get('capabilities', []):
                matching_agents.append(agent_config['id'])
        return matching_agents
    
    def route_query(self, query: str) -> str:
        query_lower = query.lower()
        
        best_match = None
        highest_priority = float('inf')
        
        for rule in self.routing_rules:
            keywords = rule.get('keywords', [])
            priority = rule.get('priority', 999)
            
            if any(keyword in query_lower for keyword in keywords):
                if priority < highest_priority:
                    highest_priority = priority
                    best_match = rule.get('agent')
        
        return best_match or self.default_agent
    
    def get_agent_card(self, agent_key: str) -> Optional[AgentCard]:
        config = self.get_agent_config(agent_key)
        if not config:
            return None
        
        return AgentCard(
            agent_id=config['id'],
            name=config['name'],
            description=config['description'],
            capabilities=config['capabilities'],
            agent_type=config['type']
        )
    
    def list_all_agents(self) -> Dict[str, Dict]:
        return self.agents
    
    def get_agent_capabilities(self, agent_key: str) -> List[str]:
        config = self.get_agent_config(agent_key)
        return config.get('capabilities', []) if config else []
    
    def get_agents_by_type(self, agent_type: str) -> List[str]:
        matching_agents = []
        for agent_key, agent_config in self.agents.items():
            if agent_config.get('type') == agent_type:
                matching_agents.append(agent_config['id'])
        return matching_agents
    
    def is_agent_available(self, agent_key: str) -> bool:
        config = self.get_agent_config(agent_key)
        return config is not None
    
    def get_supervisor_config(self) -> Dict[str, Any]:
        return self.supervisor_config
    
    def get_routing_rules(self) -> List[Dict]:
        return self.routing_rules
