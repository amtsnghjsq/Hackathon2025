import asyncio
import json
import os
from typing import Dict, Any, Optional
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from supervisor_agent import SupervisorAgent
import uvicorn

# Initialize FastAPI app
app = FastAPI(
    title="Supervisor Agent API",
    description="API for interfacing with the Supervisor Agent",
    version="1.0.0"
)

# Configure CORS for React UI
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],  # React dev server
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global supervisor instance
supervisor: Optional[SupervisorAgent] = None

# Request/Response models
class QueryRequest(BaseModel):
    message: str
    session_id: Optional[str] = None

class QueryResponse(BaseModel):
    response: str
    session_id: Optional[str] = None
    status: str = "success"

class StatusResponse(BaseModel):
    agent_id: str
    name: str
    active_agents: int
    total_tasks: int
    available_capabilities: list
    status: str = "active"

class CapabilitiesResponse(BaseModel):
    capabilities: list
    agents: Dict[str, Any]

class ErrorResponse(BaseModel):
    error: str
    status: str = "error"

@app.on_event("startup")
async def startup_event():
    """Initialize the supervisor agent on startup"""
    global supervisor
    try:
        print("🚀 Starting Supervisor Agent API...")
        supervisor = SupervisorAgent("agents.yaml")
        agent_count = await supervisor.initialize()
        print(f"✅ Supervisor Agent API ready with {agent_count} agents")
    except Exception as e:
        print(f"❌ Failed to initialize supervisor: {e}")
        raise

@app.get("/", response_model=Dict[str, str])
async def root():
    """Health check endpoint"""
    return {
        "message": "Supervisor Agent API is running",
        "status": "healthy",
        "version": "1.0.0"
    }

@app.get("/health", response_model=Dict[str, str])
async def health_check():
    """Detailed health check"""
    if supervisor is None:
        raise HTTPException(status_code=503, detail="Supervisor not initialized")
    
    return {
        "status": "healthy",
        "supervisor": "active",
        "agents": str(len(supervisor.registry.list_all_agents()))
    }

@app.post("/query", response_model=QueryResponse)
async def query_supervisor(request: QueryRequest):
    """Main endpoint for querying the supervisor agent"""
    if supervisor is None:
        raise HTTPException(status_code=503, detail="Supervisor not initialized")
    
    try:
        print(f"📝 Received query: {request.message}")
        response = await supervisor.route_and_execute(request.message)
        
        return QueryResponse(
            response=response,
            session_id=request.session_id,
            status="success"
        )
    except Exception as e:
        print(f"❌ Query failed: {e}")
        raise HTTPException(status_code=500, detail=f"Query failed: {str(e)}")

@app.get("/status", response_model=StatusResponse)
async def get_status():
    """Get supervisor agent status"""
    if supervisor is None:
        raise HTTPException(status_code=503, detail="Supervisor not initialized")
    
    try:
        status = supervisor.get_status()
        return StatusResponse(**status)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get status: {str(e)}")

@app.get("/capabilities", response_model=CapabilitiesResponse)
async def get_capabilities():
    """Get available capabilities and agents"""
    if supervisor is None:
        raise HTTPException(status_code=503, detail="Supervisor not initialized")
    
    try:
        capabilities = supervisor.get_all_capabilities()
        agents = supervisor.registry.list_all_agents()
        
        # Format agent info for response
        agent_info = {}
        for key, config in agents.items():
            agent_info[key] = {
                "id": config.get("id"),
                "name": config.get("name"),
                "type": config.get("type"),
                "description": config.get("description"),
                "capabilities": config.get("discovered_capabilities", config.get("capabilities", []))
            }
        
        return CapabilitiesResponse(
            capabilities=capabilities,
            agents=agent_info
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get capabilities: {str(e)}")

@app.get("/agents", response_model=Dict[str, Any])
async def get_agents():
    """Get list of available agents"""
    if supervisor is None:
        raise HTTPException(status_code=503, detail="Supervisor not initialized")
    
    try:
        agents = supervisor.registry.list_all_agents()
        return {"agents": agents}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get agents: {str(e)}")

if __name__ == "__main__":
    # Run the API server
    uvicorn.run(
        "api_server:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )
