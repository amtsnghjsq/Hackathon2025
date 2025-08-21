import os
import boto3
import json
import time
import uuid
import asyncio
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, Any, List, Optional, AsyncGenerator
from dotenv import load_dotenv
from botocore.exceptions import ClientError

load_dotenv()


class BedrockAgentClient:
    def __init__(self, agent_id=None, region=None):
        self.agent_id = agent_id or "bedrock-agent-001"  # Our internal ID
        self.region = region or os.getenv('AWS_REGION', 'us-west-2')

        # Your actual Bedrock agent details
        self.bedrock_agent_id = os.getenv('BEDROCK_AGENT_ID', '6UIP6AIMXF')  # Agent ID
        self.agent_alias_id = os.getenv('BEDROCK_AGENT_ALIAS_ID', 'XPAAFIXWVU')   # Alias ID

        # AWS credentials
        aws_access_key_id = os.getenv('AWS_ACCESS_KEY_ID')
        aws_secret_access_key = os.getenv('AWS_SECRET_ACCESS_KEY')
        aws_session_token = os.getenv('AWS_SESSION_TOKEN')

        # Initialize AWS Bedrock Agent Runtime client
        self.client = boto3.client(
            'bedrock-agent-runtime',
            region_name=self.region,
            aws_access_key_id=aws_access_key_id,
            aws_secret_access_key=aws_secret_access_key,
            aws_session_token=aws_session_token
        )

        # Thread pool for async execution of synchronous AWS calls
        self.executor = ThreadPoolExecutor(max_workers=4)
    
    def _invoke_agent(self, user_message: str, session_id: str, enable_trace: bool = False) -> Dict[str, Any]:
        """Invoke Bedrock agent - runs in thread pool"""
        return self.client.invoke_agent(
            agentId=self.bedrock_agent_id,
            agentAliasId=self.agent_alias_id,
            sessionId=session_id,
            inputText=user_message,
            enableTrace=enable_trace
        )

    async def query(self, user_message: str) -> str:
        """Main method for supervisor integration - calls your actual Bedrock agent"""
        start_time = time.time()
        print(f"🤖 Starting Bedrock agent call...")

        try:
            session_id = self._generate_session_id()

            # Run the synchronous AWS call in a thread pool to avoid blocking
            invoke_start = time.time()
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                self.executor,
                self._invoke_agent,
                user_message,
                session_id,
                True
            )
            invoke_duration = time.time() - invoke_start
            print(f"   • Bedrock invoke_agent: {invoke_duration:.3f}s")

            # Process streaming response
            stream_start = time.time()
            result = ""
            for event in response['completion']:
                if 'chunk' in event:
                    chunk = event['chunk']
                    if 'bytes' in chunk:
                        result += chunk['bytes'].decode('utf-8')

            stream_duration = time.time() - stream_start
            print(f"   • Response streaming: {stream_duration:.3f}s")

            total_duration = time.time() - start_time
            print(f"   • Total Bedrock time: {total_duration:.3f}s")

            return result.strip()

        except ClientError as e:
            error_code = e.response['Error']['Code']

            if error_code == 'ThrottlingException':
                raise Exception("Bedrock agent is being throttled. Please try again later.")
            elif error_code == 'ValidationException':
                raise Exception(f"Invalid agent request: {e.response['Error']['Message']}")
            elif error_code == 'ResourceNotFoundException':
                raise Exception(f"Bedrock agent not found: {self.bedrock_agent_id}")
            else:
                raise Exception(f"Bedrock agent error: {e.response['Error']['Message']}")

        except Exception as e:
            raise Exception(f"Error calling Bedrock agent: {str(e)}")

    async def query_stream(self, user_message: str) -> AsyncGenerator[str, None]:
        """Real streaming from Bedrock agent"""
        try:
            session_id = self._generate_session_id()

            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                self.executor,
                self._invoke_agent,
                user_message,
                session_id,
                False
            )

            for event in response['completion']:
                if 'chunk' in event:
                    chunk = event['chunk']
                    if 'bytes' in chunk:
                        chunk_text = chunk['bytes'].decode('utf-8')
                        yield chunk_text
                elif 'trace' in event:
                    continue
                elif 'returnControl' in event:
                    continue

        except ClientError as e:
            error_code = e.response['Error']['Code']
            if error_code == 'ThrottlingException':
                yield "⚠️ Bedrock agent is being throttled."
            elif error_code == 'ValidationException':
                yield f"❌ Invalid request: {e.response['Error']['Message']}"
            elif error_code == 'ResourceNotFoundException':
                yield f"❌ Agent not found: {self.bedrock_agent_id}"
            else:
                yield f"❌ Bedrock error: {e.response['Error']['Message']}"

        except Exception as e:
            yield f"❌ Error: {str(e)}"

    def _generate_session_id(self) -> str:
        """Generate a unique session ID"""
        import uuid
        return str(uuid.uuid4())
    
    def get_capabilities(self) -> List[str]:
        """Return list of capabilities for supervisor"""
        return [
            "bedrock_agent_invoke",
            "ai_text_generation", 
            "knowledge_base_query"
        ]
    
    def get_agent_card(self) -> Dict[str, Any]:
        """Return agent metadata for supervisor"""
        return {
            "agent_id": self.agent_id,
            "name": "Amazon Bedrock Agent",
            "description": "AI agent powered by Amazon Bedrock",
            "capabilities": self.get_capabilities(),
            "agent_type": "BedrockAgent",
            "version": "1.0.0",
            "status": "active"
        }
