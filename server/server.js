/* Local Bedrock Agent Runtime proxy with SSE */
const express = require('express');
const cors = require('cors');
const dotenv = require('dotenv');
const { BedrockAgentRuntimeClient, InvokeAgentCommand } = require('@aws-sdk/client-bedrock-agent-runtime');

dotenv.config();

const PORT = process.env.PORT || 7800;
const AWS_REGION = process.env.AWS_REGION || process.env.AWS_DEFAULT_REGION || 'us-east-1';
const AWS_ACCESS_KEY_ID = process.env.AWS_ACCESS_KEY_ID || '';
const AWS_SECRET_ACCESS_KEY = process.env.AWS_SECRET_ACCESS_KEY || '';
const AWS_SESSION_TOKEN = process.env.AWS_SESSION_TOKEN || '';
const AGENT_ID = process.env.BEDROCK_AGENT_ID || process.env.AGENT_ID || '';
const AGENT_ALIAS_ID = process.env.BEDROCK_AGENT_ALIAS_ID || process.env.AGENT_ALIAS_ID || '';

const app = express();
app.use(cors());
app.use(express.json({ limit: '1mb' }));

app.get('/health', (_req, res) => {
  res.json({ ok: true });
});

app.post('/v1/chat/stream', async (req, res) => {
  if (!AGENT_ID || !AGENT_ALIAS_ID) {
    res.status(500).json({ error: 'BEDROCK_AGENT_ID and BEDROCK_AGENT_ALIAS_ID must be set on server' });
    return;
  }

  const prompt = String(req.body?.prompt || '').trim();
  const sessionId = String(req.body?.sessionId || '').trim() || randomId();
  const enableTrace = Boolean(req.body?.enableTrace ?? true);

  if (!prompt) {
    res.status(400).json({ error: 'prompt is required' });
    return;
  }

  const clientConfig = { region: AWS_REGION };
  if (AWS_ACCESS_KEY_ID && AWS_SECRET_ACCESS_KEY) {
    clientConfig.credentials = {
      accessKeyId: AWS_ACCESS_KEY_ID,
      secretAccessKey: AWS_SECRET_ACCESS_KEY,
      sessionToken: AWS_SESSION_TOKEN || undefined,
    };
  }
  const client = new BedrockAgentRuntimeClient(clientConfig);

  res.setHeader('Content-Type', 'text/event-stream; charset=utf-8');
  res.setHeader('Cache-Control', 'no-cache, no-transform');
  res.setHeader('Connection', 'keep-alive');
  res.setHeader('X-Accel-Buffering', 'no');
  if (typeof res.flushHeaders === 'function') {
    res.flushHeaders();
  }
  // Send an initial comment + padding to defeat potential buffering
  try { res.write(`: init\n:\n:${' '.repeat(2048)}\n\n`); } catch {}

  // Keep-alive ping to encourage proxies/clients to flush
  const keepAlive = setInterval(() => {
    try { res.write(': keep-alive\n\n'); } catch {}
  }, 10000);

  const sendDelta = (text) => {
    if (typeof text !== 'string' || text.length === 0) return;
    res.write(`data: ${JSON.stringify({ text })}\n\n`);
  };
  const sendDone = () => { res.write('data: [DONE]\n\n'); res.end(); };

  try {
    const command = new InvokeAgentCommand({
      agentId: AGENT_ID,
      agentAliasId: AGENT_ALIAS_ID,
      inputText: prompt,
      sessionId,
      enableTrace,
      streamingConfigurations: {
        applyGuardrailInterval: 10,
        streamFinalResponse: true,
      },
    });
    const response = await client.send(command);
    if (!response?.completion || typeof response.completion[Symbol.asyncIterator] !== 'function') {
      res.status(500).json({ error: 'No streaming completion received from Bedrock Agent' });
      return;
    }
    for await (const event of response.completion) {
      if (event?.chunk?.bytes) {
        const text = Buffer.from(event.chunk.bytes).toString('utf8');
        if (text) {
          res.write(`data: ${JSON.stringify({ text })}\n\n`);
          if (typeof res.flush === 'function') {
            try { res.flush(); } catch {}
          }
        }
      }
      if (event?.trace?.trace) {
        // Optionally forward traces as comments; disabled by default
        // res.write(`: ${JSON.stringify(event.trace.trace)}\n\n`);
      }
    }
    clearInterval(keepAlive);
    sendDone();
  } catch (err) {
    console.error('[Bedrock Server] Error:', err);
    try {
      clearInterval(keepAlive);
      res.status(500).json({ error: err?.message || String(err) });
    } catch {}
  }
});

function randomId() {
  return Math.random().toString(36).slice(2) + Math.random().toString(36).slice(2);
}

app.listen(PORT, () => {
  console.log(`[Bedrock Server] Listening on http://127.0.0.1:${PORT}`);
});


