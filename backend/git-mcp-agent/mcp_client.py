import httpx
import json


class GitHubMCPClient:
    def __init__(self, github_token, toolsets=None, readonly=False):
        self.github_token = github_token
        self.toolsets = toolsets or ["all"]  # Default to all tools
        self.readonly = readonly

        # Build URL based on toolsets
        if "all" in self.toolsets:
            self.base_url = "https://api.githubcopilot.com/mcp/"
        else:
            # Use specific toolset (take first one for now)
            toolset = self.toolsets[0]
            self.base_url = f"https://api.githubcopilot.com/mcp/x/{toolset}/"

        if readonly:
            self.base_url = self.base_url.rstrip('/') + "/readonly/"

        self.headers = {
            "Authorization": f"Bearer {github_token}",
            "Content-Type": "application/json",
            "User-Agent": "GitHub-MCP-Client/1.0"
        }

        # Add toolset headers if multiple toolsets specified
        if len(self.toolsets) > 1 and "all" not in self.toolsets:
            self.headers['X-MCP-Toolsets'] = ','.join(self.toolsets)

        # Always set readonly mode for safety
        self.headers['X-MCP-Readonly'] = 'true'

        self.session = None
        self.tools = {}
    
    async def initialize(self):
        self.session = httpx.AsyncClient(timeout=60.0)
        try:
            # Step 1: Initialize session and capture session ID from header
            init_response = await self.session.post(
                self.base_url,
                headers=self.headers,
                json={
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "initialize",
                    "params": {
                        "protocolVersion": "2024-11-05",
                        "capabilities": {
                            "roots": {
                                "listChanged": True
                            },
                            "sampling": {}
                        },
                        "clientInfo": {
                            "name": "github-agent",
                            "version": "1.0.0"
                        }
                    }
                }
            )

            if init_response.status_code != 200:
                return 0

            # Extract session ID from response header
            session_id = init_response.headers.get('Mcp-Session-Id')
            if session_id:
                self.headers['Mcp-Session-Id'] = session_id

            # Step 2: Send initialized notification with session ID
            await self.session.post(
                self.base_url,
                headers=self.headers,
                json={
                    "jsonrpc": "2.0",
                    "method": "notifications/initialized"
                }
            )

            # Step 3: Get tools list with session ID
            tools_response = await self.session.post(
                self.base_url,
                headers=self.headers,
                json={
                    "jsonrpc": "2.0",
                    "id": 2,
                    "method": "tools/list",
                    "params": {}
                }
            )

            print(f"Tools list response: {tools_response.status_code}")

            if tools_response.status_code == 200:
                data = tools_response.json()
                if "result" in data and "tools" in data["result"]:
                    for tool in data["result"]["tools"]:
                        self.tools[tool["name"]] = {
                            "description": tool["description"],
                            "parameters": tool["inputSchema"]["properties"],
                            "required": tool["inputSchema"].get("required", [])
                        }
                    return len(self.tools)
                elif "error" in data:
                    print(f"MCP error: {data['error']}")
                    return 0
            else:
                print(f"Tools list failed: {tools_response.text}")

            return 0

        except Exception as e:
            print(f"MCP connection failed: {e}")
            return 0

    def get_tools_description(self):
        desc = "Available GitHub tools:\n"
        for name, info in self.tools.items():
            params = []
            for param_name, param_info in info["parameters"].items():
                param_type = param_info.get("type", "string")
                required = "(required)" if param_name in info["required"] else "(optional)"
                params.append(f"{param_name}: {param_type} {required}")

            params_str = ", ".join(params)
            desc += f"- {name}({params_str}): {info['description']}\n"

        return desc

    async def call_tool(self, tool_name, arguments):
        if not self.session:
            raise Exception("MCP session not initialized")

        response = await self.session.post(
            self.base_url,
            headers=self.headers,
            json={
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {
                    "name": tool_name,
                    "arguments": arguments
                }
            }
        )

        if response.status_code != 200:
            raise Exception(f"Tool call failed: {response.status_code}")

        data = response.json()
        if "result" in data:
            return data["result"]
        elif "error" in data:
            raise Exception(f"Tool error: {data['error']}")
        else:
            return data
