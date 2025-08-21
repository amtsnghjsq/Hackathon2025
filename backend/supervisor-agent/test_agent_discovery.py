#!/usr/bin/env python3
import asyncio
import sys
import os

# Add git-mcp-agent to path
sys.path.append('/Users/yashac/code/git-mcp-agent')

from supervisor_agent import SupervisorAgent
from agent import GitHubAgent


async def test_agent_discovery():
    print("🔍 Testing Agent Discovery and Communication")
    print("=" * 50)
    
    # Initialize supervisor
    print("1. Initializing Supervisor Agent...")
    supervisor = SupervisorAgent()
    await supervisor.initialize()
    
    # Initialize actual GitHub agent
    print("\n2. Initializing actual GitHub Agent...")
    try:
        github_agent = GitHubAgent(readonly=True)
        tool_count = await github_agent.initialize()
        print(f"   ✅ GitHub Agent initialized with {tool_count} tools")
        
        # Get agent capabilities
        capabilities = github_agent.get_capabilities()
        print(f"   📋 GitHub Agent Capabilities: {capabilities}")
        
        # Get agent card
        agent_card = github_agent.get_agent_card()
        print(f"   🃏 Agent Card: {agent_card['name']} ({agent_card['agent_type']})")
        
    except Exception as e:
        print(f"   ❌ Failed to initialize GitHub Agent: {e}")
        return
    
    # Test if supervisor can see the GitHub agent
    print("\n3. Testing Supervisor's Agent Registry...")
    registry_agents = supervisor.registry.list_all_agents()
    print(f"   📚 Supervisor knows about {len(registry_agents)} agent types:")
    for key, config in registry_agents.items():
        print(f"     • {config['name']} ({config['type']})")
    
    # Test routing
    print("\n4. Testing Query Routing...")
    test_queries = [
        "search for payment repositories",
        "find issues in the main repo",
        "get user information"
    ]
    
    for query in test_queries:
        target = supervisor.registry.route_query(query)
        print(f"   Query: '{query}' → Routes to: {target}")
    
    # Test direct A2A communication
    print("\n5. Testing Direct A2A Communication...")
    test_message = {
        'sender_id': supervisor.agent_id,
        'recipient_id': github_agent.agent_id,
        'message_type': 'task_request',
        'content': {
            'task_id': 'discovery-test-001',
            'description': 'get my GitHub user information',
            'parameters': {'action': 'get_me'}
        }
    }
    
    print(f"   📤 Sending A2A message to GitHub Agent...")
    response = await github_agent.receive_message(test_message)
    
    if response:
        print(f"   📥 ✅ Response received!")
        print(f"      Message Type: {response.get('message_type')}")
        print(f"      Status: {response.get('content', {}).get('status')}")
        result = response.get('content', {}).get('result', '')
        if result:
            print(f"      Result Preview: {result[:150]}...")
    else:
        print(f"   ❌ No response received")
    
    print("\n6. Checking if agents can discover each other...")
    print(f"   Supervisor Agent ID: {supervisor.agent_id}")
    print(f"   GitHub Agent ID: {github_agent.agent_id}")
    print(f"   Can supervisor send to GitHub: {await supervisor.a2a.send_message(None)}")
    print(f"   Can GitHub send to supervisor: {await github_agent.send_message('supervisor-001', 'ping', {})}")


if __name__ == "__main__":
    asyncio.run(test_agent_discovery())
