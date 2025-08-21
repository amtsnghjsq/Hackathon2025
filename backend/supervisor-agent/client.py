import boto3
import json
import os
from dotenv import load_dotenv

load_dotenv(override=True)


class BedrockClient:
    def __init__(self, region="us-east-1", model_id=None):
        aws_access_key_id = os.getenv('AWS_ACCESS_KEY_ID')
        aws_secret_access_key = os.getenv('AWS_SECRET_ACCESS_KEY')
        aws_session_token = os.getenv('AWS_SESSION_TOKEN')

        self.model_id = (
            model_id or
            os.getenv('AWS_BEDROCK_MODEL_ID') or
            "us.anthropic.claude-3-5-sonnet-20241022-v2:0"
        )

        self.bedrock = boto3.client(
            'bedrock-runtime',
            region_name=region,
            aws_access_key_id=aws_access_key_id,
            aws_secret_access_key=aws_secret_access_key,
            aws_session_token=aws_session_token
        )

    async def chat(self, messages):
        system_message = ""
        user_messages = []

        for msg in messages:
            if msg["role"] == "system":
                system_message = msg["content"]
            else:
                user_messages.append(msg)

        if not user_messages:
            user_messages = [{"role": "user", "content": "Hello"}]

        request_body = {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 4000,
            "messages": user_messages
        }

        if system_message:
            request_body["system"] = system_message

        response = self.bedrock.invoke_model(
            modelId=self.model_id,
            body=json.dumps(request_body)
        )

        response_body = json.loads(response['body'].read())
        return response_body['content'][0]['text']
