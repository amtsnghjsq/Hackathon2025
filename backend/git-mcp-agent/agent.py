import json
import os
from typing import Dict, Any, Optional, List
from dotenv import load_dotenv
from mcp_client import GitHubMCPClient
from client import BedrockClient

load_dotenv()


class GitHubAgent:
    def __init__(self, toolsets=None, readonly=False, agent_id=None):
        self.agent_id = agent_id or "github-agent-001"

        # Configure GitHub MCP client with optional toolsets and readonly mode
        github_token = os.getenv('GITHUB_TOKEN')
        self.mcp_client = GitHubMCPClient(github_token, toolsets=toolsets, readonly=readonly)

        aws_region = os.getenv('AWS_REGION', 'us-east-1')
        aws_model_id = os.getenv('AWS_BEDROCK_MODEL_ID', 'anthropic.claude-3-5-sonnet-20241022-v2:0')
        self.bedrock_client = BedrockClient(region=aws_region, model_id=aws_model_id)
        self.conversation = []
        self._cached_tools_description = None
        self._result_cache = {}
        self._max_conversation_history = 10  # Limit conversation history

    def _get_focused_tools_description(self):
        """Return a focused list of most commonly used tools to reduce prompt size"""
        # Get all available tools and prioritize the most common ones
        available_tools = list(self.mcp_client.tools.keys())

        # Priority order for tools (if available)
        priority_tools = [
            'search_repositories', 'search_code', 'get_file_contents',
            'list_pull_requests', 'list_issues', 'search_issues',
            'get_pull_request', 'list_commits', 'get_me'
        ]

        # Use priority tools that are available, then add others up to a limit
        key_tools = []
        for tool in priority_tools:
            if tool in available_tools:
                key_tools.append(tool)

        # Add other available tools up to 15 total
        for tool in available_tools:
            if tool not in key_tools and len(key_tools) < 15:
                key_tools.append(tool)

        focused_desc = f"Available GitHub MCP Tools ({len(available_tools)} total, showing {len(key_tools)} key tools):\n"
        for tool_name in key_tools:
            tool_info = self.mcp_client.tools[tool_name]
            params = []
            for param_name, param_info in tool_info["parameters"].items():
                param_type = param_info.get("type", "string")
                required = "(required)" if param_name in tool_info["required"] else "(optional)"
                params.append(f"{param_name}: {param_type} {required}")
            params_str = ", ".join(params)
            focused_desc += f"- {tool_name}({params_str}): {tool_info['description']}\n"

        return focused_desc
    
    async def initialize(self):
        return await self.mcp_client.initialize()
    
    async def plan_tools(self, user_query):
        # Cache tools description to avoid regenerating it every time
        if not hasattr(self, '_cached_tools_description'):
            self._cached_tools_description = self.mcp_client.get_tools_description()

        # Use a more focused tool description for planning
        focused_tools = self._get_focused_tools_description()

        # Get current configuration info
        toolsets_info = ", ".join(self.mcp_client.toolsets)
        readonly_info = "readonly" if self.mcp_client.readonly else "read-write"
        total_tools = len(self.mcp_client.tools)

        planning_prompt = f"""You are a GitHub Agent for Juniper Square with access to their private GitHub organization through MCP tools.

## Your Current Configuration
- Mode: {readonly_info}
- Toolsets: {toolsets_info}
- Available tools: {total_tools}
- MCP Server: {self.mcp_client.base_url}

## Your Capabilities
- **RESTRICTED TO**: Juniper Square organization (junipersquare) ONLY
- Access to 284+ private repositories in the Juniper Square organization
- GitHub MCP tools for comprehensive repository operations within junipersquare org
- Authentication to search code, files, issues, PRs, and repository metadata within junipersquare

## Key Repositories Context
Juniper Square develops financial technology solutions with key services:
- **payments-backend**: TypeScript payment processing system
- **compliance-backend**: Python compliance service (49 open issues)
- **fund-admin-backend**: Python fund administration service
- **document-indexer**: Python document processing
- **main**: Primary Python repository (179 open issues)
- **insights-ai**: AI-related services
- And 280+ other repositories

## Repository Discovery (Juniper Square ONLY)
Use `search_repositories` with org:junipersquare to find relevant repositories:
- Always include "org:junipersquare" in search queries
- For specific repo names: search "repo_name org:junipersquare"
- For service types: search "backend org:junipersquare" or
  "frontend org:junipersquare"
- For technologies: search "language:python org:junipersquare"
- For user contributions: search "author:username org:junipersquare"
- NEVER search outside the junipersquare organization

## Most Used Tools
- `search_users`: Find users by name/username (e.g., "Wilson", "john.doe")
- `search_repositories`: Find repos by name/description
- `search_code`: Search code content across repositories
- `get_file_contents`: Retrieve specific file contents (needs owner, repo, path)
- `list_pull_requests`: Get PRs for a repository
- `list_issues`: Get repository issues
- `search_issues`: Search issues/PRs across organization
- `get_teams`: Get team information and members

## Available Tools
{focused_tools}

## Task
Analyze this user query and determine which tools to execute:

**User Query:** "{user_query}"

## Decision Rules
1. **Repository ownership/who owns** → Use `list_commits` to find recent contributors, then `search_users` for details
2. **User/team questions** → Use `search_users` with partial names (e.g., "Yasha" to find "Yasha*"), `get_teams` for team info
3. **User contributions** → Use `search_issues` and `search_pull_requests` with author filters, try partial name matches
4. **Repository questions** → Use `search_repositories` or specific repo tools
5. **Code/file content searches** → Use `search_code` with query parameter
6. **Specific file requests** → Use `get_file_contents` (needs exact path)
7. **Issues/PRs questions** → Use `list_issues`, `search_issues`, or `list_pull_requests`
8. **General Git/GitHub questions** → No tools needed (set needs_tools: false)

## Required Response Format (JSON only)
{{
    "needs_tools": true/false,
    "tool_calls": [
        {{"name": "exact_tool_name", "arguments": {{"owner": "junipersquare", "repo": "repo_name", "query": "search_term"}}}}
    ],
    "reasoning": "Brief explanation of tool choice and parameters"
}}

**Important:** Always use owner: "junipersquare" for repository operations."""

        messages = [{"role": "system", "content": planning_prompt}]
        if self.conversation:
            recent_history = self.conversation[-4:]
            history_text = "\n".join([f"{msg['role']}: {msg['content']}" for msg in recent_history])
            messages.append({"role": "user", "content": f"Recent conversation:\n{history_text}\n\nCurrent query: {user_query}"})

        response = await self.bedrock_client.chat(messages)

        try:
            return json.loads(response)
        except:
            return {"needs_tools": False, "tool_calls": [], "reasoning": "Failed to parse plan"}
    
    async def execute_tools(self, tool_calls):
        results = []

        for tool_call in tool_calls:
            tool_name = tool_call["name"]
            arguments = tool_call["arguments"]

            # Check cache for read-only operations
            cache_key = None
            cacheable_tools = [
                'search_repositories', 'search_code', 'get_file_contents',
                'list_issues', 'get_me'
            ]
            if tool_name in cacheable_tools:
                cache_key = self._get_cache_key(tool_name, arguments)
                if cache_key in self._result_cache:
                    results.append(self._result_cache[cache_key])
                    continue

            if tool_name not in self.mcp_client.tools:
                error_result = {
                    "tool": tool_name,
                    "error": f"Tool '{tool_name}' not available"
                }
                results.append(error_result)
                continue

            tool_info = self.mcp_client.tools[tool_name]
            missing_params = [p for p in tool_info["required"] if p not in arguments]

            if missing_params:
                error_result = {
                    "tool": tool_name,
                    "error": f"Missing required parameters: {missing_params}"
                }
                results.append(error_result)
                continue

            try:
                result = await self.mcp_client.call_tool(tool_name, arguments)
                tool_result = {
                    "tool": tool_name,
                    "arguments": arguments,
                    "result": result
                }
                results.append(tool_result)

                # Cache successful read-only results
                if cache_key:
                    self._result_cache[cache_key] = tool_result
                    # Limit cache size
                    if len(self._result_cache) > 50:
                        # Remove oldest entries
                        oldest_keys = list(self._result_cache.keys())[:10]
                        for key in oldest_keys:
                            del self._result_cache[key]

            except Exception as e:
                error_result = {
                    "tool": tool_name,
                    "arguments": arguments,
                    "error": str(e)
                }
                results.append(error_result)

        return results
    
    async def generate_response(self, user_query, tool_results):
        # Get current configuration for context
        toolsets_info = ", ".join(self.mcp_client.toolsets)
        readonly_info = "readonly" if self.mcp_client.readonly else "read-write"
        total_tools = len(self.mcp_client.tools)

        response_prompt = f"""You are a GitHub Agent for Juniper Square, a financial technology company. You have access to their private GitHub organization with 284+ repositories and have executed GitHub MCP tools to retrieve data.

## Current Configuration
- Mode: {readonly_info}
- Toolsets: {toolsets_info}
- Available tools: {total_tools}

## Context
Juniper Square develops financial technology solutions with key services including:
- **payments-backend**: TypeScript payment processing system
- **compliance-backend**: Python compliance service (49 open issues)
- **fund-admin-backend**: Python fund administration service
- **document-indexer**: Python document processing
- **main**: Primary Python repository (179 open issues)
- **insights-ai**: AI-related services
- And 280+ other repositories

## User Request
"{user_query}"

## GitHub Data Retrieved
{json.dumps(tool_results, indent=2)}

## Response Guidelines
**Structure your response with:**
1. **Clear heading** summarizing what was found
2. **Key findings** with bullet points or numbered lists
3. **Code examples** in proper markdown code blocks with language tags
4. **Repository context** - explain which repos and why they're relevant
5. **Actionable next steps** - what the user can do with this information

**For Repository Ownership/Help Questions:**
- Use list_commits to find recent contributors (last 10-20 commits)
- Use get_pull_request_* tools to find frequent reviewers/approvers
- Look for team assignments in repository settings if available
- Show actual contributor names from the data, not generic suggestions
- If no CODEOWNERS file, use team information and repository settings to identify responsible teams
- Keep it factual and concise - provide actual names from the GitHub data

**For Name/User Searches:**
- If exact match not found, show closest matching names from the actual data
- Use partial name matching (e.g., "Yasha" might match "Yasha Chaudhary" or "yashabc")
- Show actual users found in the organization, even if not exact matches
- Provide real results rather than "no results found" messages

**For Code Search Results:**
- Always include the full file path for each code result
- Format as: `repository/path/to/file.ext` (e.g., `payments-backend/src/utils/validation.ts`)
- Group results by repository when showing multiple files
- Include line numbers when available from the search results
- Show relevant code snippets with proper syntax highlighting
- List ALL file names where the code is used, called, or referenced
- Include both definition files and usage/import files
- Search and include usage in BOTH frontend (FE) and backend (BE) repositories
- Cross-reference between TypeScript/JavaScript frontend and Python/other backend files
- Explain the context of why each file is relevant to the search query

**Quality standards:**
- Keep responses concise and focused (avoid information overload)
- Use clean markdown without excessive special characters
- For contact questions: List 2-3 key people maximum
- For search results: Show key findings, not exhaustive lists
- Prioritize actionable information over comprehensive data dumps
- Use simple formatting: headers, bullet points, short paragraphs

**Tone:** Direct and helpful, focused on answering the specific question.

**Response Approach:**
- Only show the recommended approach for solving the user's question
- After providing the recommended solution, ask if the user wants to see an alternate approach
- This keeps responses focused while offering additional options when needed

Generate a focused response that directly answers the user's question without
overwhelming detail."""

        # Include conversation history for context
        messages = []
        if self.conversation:
            messages.extend(self.conversation[-4:])  # Last 4 messages for context
        messages.append({"role": "system", "content": response_prompt})

        return await self.bedrock_client.chat(messages)
    
    def _manage_conversation_history(self):
        """Keep conversation history within reasonable limits"""
        if len(self.conversation) > self._max_conversation_history:
            # Keep the most recent conversations
            self.conversation = self.conversation[-self._max_conversation_history:]

    def _get_cache_key(self, tool_name, arguments):
        """Generate cache key for tool results"""
        import hashlib
        key_data = f"{tool_name}:{json.dumps(arguments, sort_keys=True)}"
        return hashlib.md5(key_data.encode()).hexdigest()

    async def query(self, user_message):
        self.conversation.append({"role": "user", "content": user_message})
        self._manage_conversation_history()

        plan = await self.plan_tools(user_message)

        if plan["needs_tools"]:
            tool_results = await self.execute_tools(plan["tool_calls"])
            response = await self.generate_response(user_message, tool_results)
        else:
            # Direct chat with optimized conversation history
            # Get current configuration for context
            toolsets_info = ", ".join(self.mcp_client.toolsets)
            readonly_info = "readonly" if self.mcp_client.readonly else "read-write"
            total_tools = len(self.mcp_client.tools)

            system_prompt = f"""You are a GitHub Agent for Juniper Square, a financial technology company. You have access to their private GitHub organization with 284+ repositories through MCP tools, but this query doesn't require tool execution.

## Your Current Configuration
- Mode: {readonly_info}
- Toolsets: {toolsets_info}
- Available tools: {total_tools}

## Your Role
Provide expert guidance on GitHub workflows, Git concepts, and development practices tailored to Juniper Square's fintech environment.

## Juniper Square Context
- **284+ private repositories** with services like payments-backend, compliance-backend, fund-admin-backend
- **Financial technology focus** requiring secure, compliant development practices
- **Multi-language codebase** (Python, TypeScript, etc.)
- **Active development** with hundreds of open issues and PRs

## What You Can Help With
- **Git/GitHub concepts**: merge vs rebase, branching strategies, workflow best practices
- **Juniper Square-specific guidance**: How to work with their repository structure
- **Development workflows**: PR processes, code review, CI/CD practices
- **Tool recommendations**: When to use specific GitHub MCP tools for tasks

## Available Tools to Suggest
When users need data from repositories, suggest these tools:
- `search_code`: "Use search_code to find files containing specific content"
- `get_file_contents`: "Use get_file_contents to retrieve a specific file"
- `search_repositories`: "Use search_repositories to find repos by name"
- `list_issues`: "Use list_issues to see open issues in a repository"

## Response Style
- **Professional but conversational**
- **Practical and actionable** advice
- **Include Juniper Square context** when relevant
- **Suggest specific tools** for follow-up actions

Provide helpful, accurate information that helps users work effectively with Juniper Square's GitHub repositories."""

            messages = [{"role": "system", "content": system_prompt}]
            # Use only recent conversation history for efficiency
            if self.conversation:
                messages.extend(self.conversation[-4:])  # Reduced from 6 to 4
            messages.append({"role": "user", "content": user_message})
            response = await self.bedrock_client.chat(messages)

        self.conversation.append({"role": "assistant", "content": response})
        return response

    def get_capabilities(self) -> List[str]:
        # Return readonly capabilities based on agent configuration
        if self.mcp_client and self.mcp_client.readonly:
            return [
                "github_repository_search",
                "github_code_search",
                "github_issue_viewing",
                "github_pull_request_viewing",
                "github_user_lookup",
                "github_team_viewing",
                "github_workflow_monitoring",
                "github_security_alerts_viewing",
                "github_notifications_viewing",
                "github_releases_viewing"
            ]
        else:
            # Full capabilities for read-write mode
            return [
                "github_repository_operations",
                "github_issue_management",
                "github_pull_request_management",
                "github_code_search",
                "github_user_management",
                "github_team_management",
                "github_workflow_management",
                "github_security_scanning",
                "github_notifications",
                "github_releases_management"
            ]

    def get_agent_card(self) -> Dict[str, Any]:
        mode = "readonly" if (self.mcp_client and self.mcp_client.readonly) else "read-write"
        description = f"GitHub agent for {mode} operations using MCP protocol"

        return {
            "agent_id": self.agent_id,
            "name": "GitHub MCP Agent",
            "description": description,
            "capabilities": self.get_capabilities(),
            "agent_type": "GitHubAgent",
            "mode": mode,
            "version": "1.0.0",
            "status": "active"
        }

    async def send_message(self, recipient_id: str, message_type: str, content: Dict[str, Any]) -> bool:
        try:
            return True
        except Exception:
            return False

    async def receive_message(self, message: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        try:
            message_type = message.get("message_type")
            if message_type == "task_request":
                task_data = message.get("content", {})
                description = task_data.get("description", "")
                result = await self.query(description)

                return {
                    "sender_id": self.agent_id,
                    "recipient_id": message.get("sender_id"),
                    "message_type": "task_response",
                    "content": {
                        "task_id": task_data.get("task_id"),
                        "status": "completed",
                        "result": result,
                        "agent_id": self.agent_id
                    }
                }
            return None
        except Exception:
            return None
