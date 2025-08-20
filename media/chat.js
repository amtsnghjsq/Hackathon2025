(function() {
  const vscode = acquireVsCodeApi();
  const chat = document.getElementById('chat');
  const prompt = document.getElementById('prompt');
  const send = document.getElementById('send');
  const cancel = document.getElementById('cancel');
  const newChat = document.getElementById('newChat');
  const status = document.getElementById('status');

  function escapeHtml(str) {
    return String(str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }

  function inlineFormat(text) {
    // inline code
    text = text.replace(/`([^`]+)`/g, '<code>$1</code>');
    // bold
    text = text.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
    // emphasis (simple)
    text = text.replace(/\*(.+?)\*/g, '<em>$1</em>');
    return text;
  }

  function markdownToHtml(md) {
    const lines = String(md || '').split(/\r?\n/);
    let html = '';
    let inCode = false;
    let inList = false;
    for (let i = 0; i < lines.length; i++) {
      let line = lines[i];
      if (line.trim().startsWith('```')) {
        if (!inCode) {
          if (inList) { html += '</ul>'; inList = false; }
          inCode = true; html += '<pre><code>';
        } else {
          inCode = false; html += '</code></pre>';
        }
        continue;
      }
      if (inCode) {
        html += escapeHtml(line) + '\n';
        continue;
      }

      if (/^\s*$/.test(line)) {
        if (inList) { html += '</ul>'; inList = false; }
        continue;
      }

      // Headings
      const h = line.match(/^(#{1,6})\s+(.*)$/);
      if (h) {
        if (inList) { html += '</ul>'; inList = false; }
        const level = h[1].length;
        const content = inlineFormat(escapeHtml(h[2]));
        html += `<h${level}>${content}</h${level}>`;
        continue;
      }

      // Unordered list
      const ul = line.match(/^\s*([*-])\s+(.*)$/);
      if (ul) {
        if (!inList) { html += '<ul>'; inList = true; }
        const content = inlineFormat(escapeHtml(ul[2]));
        html += `<li>${content}</li>`;
        continue;
      }

      // Ordered list
      const ol = line.match(/^\s*([0-9]+)\.\s+(.*)$/);
      if (ol) {
        if (!inList) { html += '<ul>'; inList = true; }
        const content = inlineFormat(escapeHtml(ol[2]));
        html += `<li>${content}</li>`;
        continue;
      }

      // Paragraph
      const content = inlineFormat(escapeHtml(line));
      html += `<p>${content}</p>`;
    }
    if (inList) html += '</ul>';
    if (inCode) html += '</code></pre>';
    return html;
  }

  function appendMessage(role, text) {
    const div = document.createElement('div');
    div.className = `msg ${role}`;
    div.innerHTML = markdownToHtml(text);
    chat.appendChild(div);
    chat.scrollTop = chat.scrollHeight;
  }

  function setBusy(isBusy, msg) {
    send.disabled = isBusy;
    cancel.disabled = !isBusy;
    status.textContent = msg || (isBusy ? 'Thinking…' : '');
  }

  function sendMessage() {
    const text = prompt.value.trim();
    if (!text) return;
    appendMessage('user', text);
    prompt.value = '';
    setBusy(true);
    vscode.postMessage({ type: 'sendMessage', text });
  }

  send.addEventListener('click', sendMessage);
  cancel.addEventListener('click', () => vscode.postMessage({ type: 'cancel' }));
  newChat.addEventListener('click', () => vscode.postMessage({ type: 'newChat' }));

  prompt.addEventListener('keydown', (e) => {
    if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') {
      e.preventDefault();
      sendMessage();
    }
  });

  // Streaming handling
  let currentAssistantEl = null;
  let currentAssistantBuffer = '';
  let currentLoader = null;
  let currentAssistantContentEl = null;
  window.addEventListener('message', (event) => {
    const msg = event.data || {};
    switch (msg.type) {
      case 'reset': {
        // Clear chat history UI and show new session id in status for visibility
        chat.innerHTML = '';
        currentAssistantEl = null;
        currentAssistantBuffer = '';
        status.textContent = `New session: ${msg.sessionId || ''}`;
        break;
      }
      case 'userMessage':
        // already rendered locally
        break;
      case 'assistantStart': {
        currentAssistantEl = document.createElement('div');
        currentAssistantEl.className = 'msg assistant empty';
        currentAssistantEl.innerHTML = '';
        currentAssistantBuffer = '';

        // Assistant header animation (persists)
        const head = document.createElement('div');
        head.className = 'assist-head';
        const headAnim = document.createElement('div');
        headAnim.className = 'anim';
        head.appendChild(headAnim);
        try {
          const auri = window.__ASSIST_ANIM_URI__;
          if (auri && window.lottie) {
            window.lottie.loadAnimation({ container: headAnim, renderer: 'svg', loop: true, autoplay: true, path: auri });
          }
        } catch {}
        currentAssistantEl.appendChild(head);

        // Content container where text will render (so header persists)
        currentAssistantContentEl = document.createElement('div');
        currentAssistantContentEl.className = 'assistant-content';
        currentAssistantEl.appendChild(currentAssistantContentEl);

        // loader placeholder (overlaid)
        currentLoader = document.createElement('div');
        currentLoader.className = 'loader';
        const animHolder = document.createElement('div');
        animHolder.className = 'anim';
        animHolder.style.width = '120px';
        animHolder.style.height = '120px';
        currentLoader.appendChild(animHolder);
        // Try to load Lottie animation for loader
        try {
          const uri = window.__LOADER_JSON_URI__;
          if (uri && window.lottie) {
            window.lottie.loadAnimation({
              container: animHolder,
              renderer: 'svg',
              loop: true,
              autoplay: true,
              path: uri
            });
          }
        } catch {}
        currentAssistantEl.appendChild(currentLoader);
        chat.appendChild(currentAssistantEl);
        chat.scrollTop = chat.scrollHeight;
        break;
      }
      case 'appendResponse': {
        if (!currentAssistantEl) {
          currentAssistantEl = document.createElement('div');
          currentAssistantEl.className = 'msg assistant';
          // ensure content container
          currentAssistantContentEl = document.createElement('div');
          currentAssistantContentEl.className = 'assistant-content';
          currentAssistantEl.appendChild(currentAssistantContentEl);
          chat.appendChild(currentAssistantEl);
        }
        if (currentLoader && currentLoader.parentElement) {
          currentLoader.parentElement.removeChild(currentLoader);
          currentLoader = null;
        }
        currentAssistantEl.classList.remove('empty');
        currentAssistantBuffer += msg.delta || '';
        if (!currentAssistantContentEl) {
          currentAssistantContentEl = document.createElement('div');
          currentAssistantContentEl.className = 'assistant-content';
          currentAssistantEl.appendChild(currentAssistantContentEl);
        }
        currentAssistantContentEl.innerHTML = markdownToHtml(currentAssistantBuffer);
        chat.scrollTop = chat.scrollHeight;
        break;
      }
      case 'assistantComplete':
        setBusy(false);
        if (currentLoader && currentLoader.parentElement) {
          currentLoader.parentElement.removeChild(currentLoader);
        }
        currentLoader = null;
        if (currentAssistantEl) currentAssistantEl.classList.remove('empty');
        currentAssistantEl = null;
        currentAssistantBuffer = '';
        currentAssistantContentEl = null;
        break;
      case 'error':
        setBusy(false);
        const err = document.createElement('div');
        err.className = 'msg error';
        err.textContent = msg.message || 'An error occurred';
        chat.appendChild(err);
        chat.scrollTop = chat.scrollHeight;
        break;
      case 'status':
        status.textContent = msg.text || '';
        break;
      default:
        break;
    }
  });
})();


