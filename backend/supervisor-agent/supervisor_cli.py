#!/usr/bin/env python3
import asyncio
from supervisor_agent import SupervisorAgent


class SupervisorCLI:
    def __init__(self, config_file: str = "agents.yaml"):
        self.supervisor = SupervisorAgent(config_file)
    
    async def initialize(self):
        print("🚀 Initializing Supervisor Agent System...")
        agent_count = await self.supervisor.initialize()
        
        status = self.supervisor.get_status()
        capabilities = status['available_capabilities']
        
        print(f"✅ Ready! Supervisor managing {agent_count} agent types.")
        print(f"🎯 Available capabilities: {len(capabilities)}")
        
        for i, capability in enumerate(capabilities, 1):
            print(f"  {i:2d}. {capability}")
        print()
    
    async def run(self):
        await self.initialize()
        
        while True:
            try:
                query = input("\n🤖 Supervisor> ").strip()
                
                if not query:
                    continue
                
                if query.lower() in ['quit', 'exit', 'q']:
                    print("👋 Goodbye!")
                    break
                
                if query.lower() in ['status', 'info']:
                    self.show_status()
                    continue
                
                print("🔄 Processing...")
                response = await self.supervisor.query(query)
                
                print(f"\n🤖 Supervisor Agent:")
                print(response)
                
            except KeyboardInterrupt:
                print("\n👋 Goodbye!")
                break
            except Exception as e:
                print(f"❌ Error: {e}")
    
    def show_status(self):
        status = self.supervisor.get_status()
        print(f"\n📊 Supervisor Status:")
        print(f"  Agent ID: {status['agent_id']}")
        print(f"  Name: {status['name']}")
        print(f"  Total Tasks Processed: {status['total_tasks']}")
        print(f"  Available Capabilities: {len(status['available_capabilities'])}")
        
        agents = self.supervisor.registry.list_all_agents()
        print(f"\n🤖 Managed Agents:")
        for agent_key, config in agents.items():
            print(f"  • {config['name']} ({config['type']})")
            print(f"    Capabilities: {', '.join(config['capabilities'][:3])}{'...' if len(config['capabilities']) > 3 else ''}")


async def main():
    import sys
    
    config_file = "agents.yaml"
    if "--config" in sys.argv:
        idx = sys.argv.index("--config")
        if idx + 1 < len(sys.argv):
            config_file = sys.argv[idx + 1]
    
    cli = SupervisorCLI(config_file)
    await cli.run()


if __name__ == "__main__":
    asyncio.run(main())
