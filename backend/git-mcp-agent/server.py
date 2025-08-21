#!/usr/bin/env python3
import asyncio
import json
from typing import Dict, Any
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import uvicorn
from agent import GitHubAgent


class QueryRequest(BaseModel):
    query: str
    parameters: Dict[str, Any] = {}


class QueryResponse(BaseModel):
    status: str
    result: str
    agent_id: str


app = FastAPI(title="GitHub MCP Agent Server")
github_agent = None


@app.on_event("startup")
async def startup_event():
    global github_agent
    print("🚀 Starting GitHub MCP Agent Server...")
    github_agent = GitHubAgent(readonly=True)
    tool_count = await github_agent.initialize()
    print(f"✅ GitHub Agent initialized with {tool_count} tools")


@app.get("/health")
async def health_check():
    if github_agent is None:
        raise HTTPException(status_code=503, detail="Agent not initialized")
    return {
        "status": "healthy",
        "agent_id": github_agent.agent_id,
        "name": "GitHub MCP Agent"
    }


@app.get("/capabilities")
async def get_capabilities():
    if github_agent is None:
        raise HTTPException(status_code=503, detail="Agent not initialized")

    # Get high-level capabilities from agent
    capabilities = github_agent.get_capabilities()

    # Get MCP tools for metadata (not exposed as capabilities)
    mcp_tools = list(github_agent.mcp_client.tools.keys()) if github_agent.mcp_client.tools else []

    return {
        "agent_id": github_agent.agent_id,
        "capabilities": capabilities,
        "description": "GitHub operations agent using MCP protocol",
        "mcp_backend": {
            "total_tools": len(mcp_tools),
            "sample_tools": mcp_tools[:5],
            "server": "GitHub MCP Server"
        },
        "agent_card": github_agent.get_agent_card()
    }


@app.post("/query")
async def process_query(request: QueryRequest) -> QueryResponse:
    if github_agent is None:
        raise HTTPException(status_code=503, detail="Agent not initialized")
    
    try:
        print(f"📥 Received query: {request.query}")
        result = await github_agent.query(request.query)
        
        return QueryResponse(
            status="completed",
            result=result,
            agent_id=github_agent.agent_id
        )
    except Exception as e:
        print(f"❌ Query failed: {e}")
        return QueryResponse(
            status="failed",
            result=f"Error: {str(e)}",
            agent_id=github_agent.agent_id
        )


@app.post("/a2a/message")
async def handle_a2a_message(message: Dict[str, Any]):
    if github_agent is None:
        raise HTTPException(status_code=503, detail="Agent not initialized")
    
    try:
        print(f"📨 Received A2A message: {message.get('message_type')}")
        response = await github_agent.receive_message(message)
        return response or {"status": "no_response"}
    except Exception as e:
        print(f"❌ A2A message failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    print("🌐 Starting GitHub MCP Agent HTTP Server on port 8001...")
    uvicorn.run(app, host="0.0.0.0", port=8001)
