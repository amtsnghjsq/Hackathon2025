#!/usr/bin/env python3
import asyncio
from agent import GitHubAgent


class GitHubCLI:
    def __init__(self, toolsets=None, readonly=True):
        self.agent = GitHubAgent(toolsets=toolsets, readonly=readonly)
    
    async def initialize(self):
        print("🚀 Initializing GitHub Agent...")
        tool_count = await self.agent.initialize()

        # Show readonly status and available tools
        readonly_status = "readonly" if self.agent.mcp_client.readonly else "read-write"
        toolsets = ", ".join(self.agent.mcp_client.toolsets)
        print(f"📋 Mode: {readonly_status}")
        print(f"🔧 Toolsets: {toolsets}")
        print(f"🌐 URL: {self.agent.mcp_client.base_url}")
        print(f"✅ Ready! Loaded {tool_count} GitHub tools.")

        # List all available tools
        if tool_count > 0:
            print("\n📚 Available tools:")
            for i, tool_name in enumerate(sorted(self.agent.mcp_client.tools.keys()), 1):
                print(f"  {i:2d}. {tool_name}")
            print()
    
    async def run(self):
        await self.initialize()
        
        while True:
            try:
                query = input("\n🐙 GitHub> ").strip()
                
                if not query:
                    continue
                
                if query.lower() in ['quit', 'exit', 'q']:
                    print("👋 Goodbye!")
                    break
                
                print("🔄 Processing...")
                response = await self.agent.query(query)
                
                print(f"\n🤖 GitHub Agent:")
                print(response)
                
            except KeyboardInterrupt:
                print("\n👋 Goodbye!")
                break
            except Exception as e:
                print(f"❌ Error: {e}")


async def main():
    import sys

    # Parse simple command line arguments
    toolsets = None
    readonly = True  # Default to readonly mode

    if "--toolsets" in sys.argv:
        idx = sys.argv.index("--toolsets")
        if idx + 1 < len(sys.argv):
            toolsets = sys.argv[idx + 1].split(",")

    if "--read-write" in sys.argv:
        readonly = False

    cli = GitHubCLI(toolsets=toolsets, readonly=readonly)
    await cli.run()


if __name__ == "__main__":
    asyncio.run(main())
