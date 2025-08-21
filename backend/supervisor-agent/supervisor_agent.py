import json
import os
import asyncio
from typing import Dict, Any, Optional, List
from dotenv import load_dotenv
from agent_registry import AgentRegistry
from a2a_protocol import A2AProtocol, AgentMessage, TaskRequest, TaskResponse, AgentCard
from client import BedrockClient
from bedrock_agent.client import BedrockAgentClient

load_dotenv()


class SupervisorAgent:
    def __init__(self, config_file: str = "agents.yaml"):
        self.agent_id = "supervisor-001"
        self.name = "Supervisor Agent"
        self.registry = AgentRegistry(config_file)
        self.a2a = A2AProtocol(self.agent_id)
        self.bedrock_client = BedrockClient()
        self.bedrock_agent_client = None
        self.conversation = []
        self.active_agents = {}
        self.task_history = {}
        
        self.a2a.register_handler("task_request", self.handle_task_request)
        self.a2a.register_handler("task_response", self.handle_task_response)
    
    async def initialize(self):
        print(f"🚀 Initializing {self.name}...")
        
        agent_configs = self.registry.list_all_agents()
        print(f"📋 Found {len(agent_configs)} agent configurations")
        
        # Discover capabilities from actual agents
        for agent_key, config in agent_configs.items():
            if config.get('endpoint', '').startswith('http'):
                try:
                    print(f"  🔍 Discovering capabilities for {config['name']}...")
                    capabilities = await self.discover_agent_capabilities(config)
                    config['discovered_capabilities'] = capabilities
                    print(f"  • {config['name']}: {len(capabilities)} capabilities discovered")
                    if capabilities:
                        print(f"    {', '.join(capabilities[:5])}{'...' if len(capabilities) > 5 else ''}")
                except Exception as e:
                    print(f"  ❌ Failed to discover capabilities for {config['name']}: {e}")
                    config['discovered_capabilities'] = []
            elif config.get('type') == 'BedrockAgent':
                # Initialize Bedrock agent client directly
                bedrock_config = config.get('config', {})
                self.bedrock_agent_client = BedrockAgentClient(
                    agent_id=config.get('id'),
                    region=bedrock_config.get('region', 'us-west-2')
                )
                print(f"  🤖 Initialized Bedrock agent: {config['name']}")

                # Get capabilities from Bedrock agent
                config['discovered_capabilities'] = self.bedrock_agent_client.get_capabilities()
                print(f"  • {config['name']}: {len(config['discovered_capabilities'])} capabilities discovered")
            else:
                print(f"  • {config['name']}: local/simulated agent")
                config['discovered_capabilities'] = []
        
        return len(agent_configs)
    
    async def discover_agent_capabilities(self, config):
        """Discover capabilities from actual agent via HTTP"""
        import httpx
        
        endpoint = config.get('endpoint')
        capabilities_url = f"{endpoint}{config.get('capabilities_endpoint', '/capabilities')}"
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(capabilities_url, timeout=10.0)
                if response.status_code == 200:
                    data = response.json()
                    capabilities = data.get('capabilities', [])
                    # Log MCP backend info if available
                    mcp_backend = data.get("mcp_backend", {})
                    if mcp_backend:
                        total_tools = mcp_backend.get("total_tools", 0)
                        print(f"    Backend: {total_tools} MCP tools from {mcp_backend.get("server", "MCP Server")}")
                    return capabilities
                else:
                    print(f"Failed to get capabilities: {response.status_code}")
                    return []
        except Exception as e:
            print(f"Error connecting to agent: {e}")
            return []
    
    def get_agent_card(self) -> AgentCard:
        return AgentCard(
            agent_id=self.agent_id,
            name=self.name,
            description="Supervisor agent that routes tasks to specialized agents",
            capabilities=[
                "task_routing",
                "agent_coordination", 
                "workflow_management",
                "multi_agent_orchestration"
            ],
            agent_type="SupervisorAgent"
        )
    
    async def handle_task_request(self, message: AgentMessage) -> Optional[AgentMessage]:
        task_data = message.content
        task_request = TaskRequest(**task_data)
        
        target_agent = self.registry.route_query(task_request.description)
        
        if target_agent and self.registry.is_agent_available(target_agent):
            result = await self.delegate_task(task_request, target_agent)
            response = TaskResponse(
                task_id=task_request.task_id,
                status="completed" if result else "failed",
                result=result,
                agent_id=self.agent_id
            )
        else:
            response = TaskResponse(
                task_id=task_request.task_id,
                status="failed",
                error=f"No suitable agent found for task",
                agent_id=self.agent_id
            )
        
        return response.to_message(message.sender_id)
    
    async def handle_task_response(self, message: AgentMessage) -> None:
        task_response = TaskResponse(**message.content)
        self.task_history[task_response.task_id] = task_response
    
    async def delegate_task(self, task: TaskRequest, target_agent: str) -> Any:
        if target_agent == "github-agent":
            return await self.execute_github_task(task)
        elif target_agent == "bedrock-agent-001":
            return await self.execute_bedrock_task(task)
        else:
            return f"Agent {target_agent} not implemented yet"
    
    async def execute_github_task(self, task: TaskRequest) -> str:
        """Execute task by calling the actual git-mcp-agent HTTP server"""
        import httpx
        
        # Get github-agent config
        agent_config = self.registry.get_agent_config("github-agent")
        if not agent_config:
            return "GitHub Agent not found in registry"
        
        endpoint = agent_config.get('endpoint')
        query_url = f"{endpoint}{agent_config.get('query_endpoint', '/query')}"
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    query_url,
                    json={"query": task.description, "parameters": task.parameters},
                    timeout=30.0
                )
                
                if response.status_code == 200:
                    data = response.json()
                    return data.get('result', 'No result from git-mcp-agent')
                else:
                    return f"Git-MCP-Agent error: {response.status_code}"
                    
        except Exception as e:
            return f"Failed to connect to github-agent: {str(e)}"

    async def execute_bedrock_task(self, task: TaskRequest) -> str:
        """Execute task by calling the Bedrock agent"""
        if not self.bedrock_agent_client:
            return "Bedrock agent not initialized"

        try:
            result = await self.bedrock_agent_client.query(task.description)
            return result
        except Exception as e:
            return f"Failed to execute Bedrock task: {str(e)}"
    
    async def route_and_execute(self, user_query: str) -> str:
        """Always route to both agents and collate responses"""
        print(f"🔄 Routing to both agents simultaneously...")

        # Create tasks for both agents
        github_task = TaskRequest(
            task_id="github-task",
            description=user_query,
            parameters={"query": user_query},
            requester_id=self.agent_id
        )

        bedrock_task = TaskRequest(
            task_id="bedrock-task",
            description=user_query,
            parameters={"query": user_query},
            requester_id=self.agent_id
        )

        # Execute both agents simultaneously
        github_result_task = asyncio.create_task(self.delegate_task(github_task, "github-agent"))
        bedrock_result_task = asyncio.create_task(self.delegate_task(bedrock_task, "bedrock-agent-001"))

        print(f"   • GitHub agent task created: {id(github_result_task)}")
        print(f"   • Bedrock agent task created: {id(bedrock_result_task)}")

        # Wait for both results
        github_result, bedrock_result = await asyncio.gather(
            github_result_task, bedrock_result_task, return_exceptions=True
        )

        # Collate responses using bedrock agent
        return await self.collate_responses(user_query, github_result, bedrock_result)

    async def collate_responses(self, query: str, github_result: Any, bedrock_result: Any) -> str:
        """Intelligently combine responses from both agents"""
        if not self.bedrock_agent_client:
            # Fallback to simple concatenation if bedrock agent not available
            github_content = github_result if not isinstance(github_result, Exception) else f"Error: {github_result}"
            bedrock_content = bedrock_result if not isinstance(bedrock_result, Exception) else f"Error: {bedrock_result}"
            return f"GitHub Agent: {github_content}\n\nBedrock Agent: {bedrock_content}"

        # Format results for collation
        github_content = github_result if not isinstance(github_result, Exception) else f"Error: {github_result}"
        bedrock_content = bedrock_result if not isinstance(bedrock_result, Exception) else f"Error: {bedrock_result}"

        collation_prompt = f"""You are a supervisor agent that intelligently combines responses from two specialized agents: a GitHub Agent (repository/code expert) and a Bedrock Agent (general AI assistant).

User Query: {query}

GitHub Agent Result: {self._format_agent_result(github_content)}

Bedrock Agent Result: {self._format_agent_result(bedrock_content)}

IMPORTANT INSTRUCTIONS:
1. PRESERVE ALL file paths, repository references, URLs, and technical details from the GitHub Agent
2. PRESERVE ALL code snippets, file names, directory structures, and git-related information exactly as provided
3. If the GitHub Agent provides specific file references, repository information, or code examples, include them verbatim
4. Combine the GitHub Agent's technical/repository knowledge with the Bedrock Agent's general knowledge
5. When both agents provide relevant information, present the GitHub Agent's technical details first, then supplement with Bedrock Agent insights
6. If the GitHub Agent has errors but the Bedrock Agent succeeds, clearly note the GitHub Agent limitation while providing the Bedrock response
7. If the GitHub Agent succeeds but provides repository-specific information, prioritize and highlight that information
8. Do not summarize or paraphrase file paths, repository names, or technical references - keep them exact
9. Only show the recommended approach and ask if the user wants to see an alternate approach

Provide a comprehensive response that leverages the specialized knowledge from both agents while preserving all technical details and references."""

        try:
            result = await self.bedrock_agent_client.query(collation_prompt)
            return result
        except Exception as e:
            # Fallback to simple combination if collation fails
            return f"GitHub Agent: {github_content}\n\nBedrock Agent: {bedrock_content}\n\n(Note: Response collation failed: {e})"

    def _format_agent_result(self, result: Any) -> str:
        """Format agent result for display"""
        if isinstance(result, Exception):
            return f"Error: {str(result)}"
        elif isinstance(result, str):
            return result
        else:
            return str(result)
    
    async def query(self, user_message: str) -> str:
        self.conversation.append({"role": "user", "content": user_message})
        
        if len(self.conversation) > 10:
            self.conversation = self.conversation[-10:]
        
        response = await self.route_and_execute(user_message)
        
        self.conversation.append({"role": "assistant", "content": response})
        return response
    
    def get_status(self) -> Dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "name": self.name,
            "active_agents": len(self.active_agents),
            "total_tasks": len(self.task_history),
            "available_capabilities": self.get_all_capabilities()
        }
    
    def get_all_capabilities(self) -> List[str]:
        all_caps = set()
        for agent_config in self.registry.list_all_agents().values():
            discovered = agent_config.get('discovered_capabilities', [])
            static = agent_config.get('capabilities', [])
            all_caps.update(discovered or static)
        return sorted(list(all_caps))
