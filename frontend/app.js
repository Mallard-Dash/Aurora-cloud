/* app.js
   Minimal, robust xterm.js frontend + panel-switching.
   Byter token via localStorage (aurora_token) eller query ?token=...
   Anpassa WS-host om din backend körs på annan host/port.
*/

(() => {
  // ---- Helpers ----
  function $el(id) { return document.getElementById(id); }
  function qs(sel) { return document.querySelector(sel); }
  function qsa(sel) { return Array.from(document.querySelectorAll(sel)); }

  // Init panel nav
  qsa('.nav button').forEach(btn => {
    btn.addEventListener('click', () => {
      qsa('.nav button').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      const target = btn.dataset.target;
      qsa('.panel').forEach(p => p.classList.remove('active'));
      const el = $el(target);
      if (el) el.classList.add('active');
      // If terminal tab opened, focus on terminal
      if (target === 'terminal') {
        setTimeout(() => {
          try { term.focus(); } catch(e){}
        }, 60);
      }
    });
  });

  // Save / load token helpers
  const TOKEN_KEY = 'aurora_token';
  function getTokenFromUrl() {
    try {
      const u = new URL(location.href);
      return u.searchParams.get('token');
    } catch(e) { return null; }
  }
  function saveToken(token) {
    if (!token) { localStorage.removeItem(TOKEN_KEY); return; }
    localStorage.setItem(TOKEN_KEY, token);
  }
  function loadToken() {
    return localStorage.getItem(TOKEN_KEY) || getTokenFromUrl() || null;
  }

  // Populate token input
  const tokenInput = $el('tokenInput');
  const saveTokenBtn = $el('saveToken');
  tokenInput.value = loadToken() || '';
  saveTokenBtn.addEventListener('click', () => {
    saveToken(tokenInput.value.trim() || null);
    tokenInput.value = loadToken() || '';
    alert('Token sparad lokalt.');
  });

  // Quick actions
  $el('sendCtrlC').addEventListener('click', () => {
    sendCtrlC();
  });
  $el('clearTerminal').addEventListener('click', () => {
    term.clear();
    // also send clear sequence so shell gets it
    // but not strictly necessary
    // term.write('\x0c');
  });
  $el('reconnectBtn').addEventListener('click', () => {
    reconnectWS();
  });

  // ---- xterm setup ----
  const { Terminal } = window;
  const { FitAddon } = window;
  if (!Terminal || !FitAddon) {
    console.error('xterm.js not loaded');
    return;
  }

  const term = new Terminal({
    cursorBlink: true,
    fontFamily: 'monospace',
    fontSize: 13,
    scrollback: 10000,
  });
  const fitAddon = new FitAddon();
  term.loadAddon(fitAddon);

  const termContainer = $el('terminalContainer');
  term.open(termContainer);
  fitAddon.fit();

  // send resize when terminal size changes
  function sendResize() {
    if (!ws || ws.readyState !== WebSocket.OPEN) return;
    const cols = term.cols;
    const rows = term.rows;
    const msg = JSON.stringify({ type: 'resize', cols, rows });
    ws.send(msg);
  }

  window.addEventListener('resize', () => {
    fitAddon.fit();
    sendResize();
  });

  // ---- WebSocket handling ----
  let ws = null;
  let reconnectTimer = null;
  const RECONNECT_MS = 1000;

  // Build WS URL (uses same host as page by default)
  function buildWsUrl() {
    // If you want an explicit host:port, change here
    const protocol = (location.protocol === 'https:') ? 'wss' : 'ws';
    const host = location.host; // uses same host:port as served page
    // include token if present as query param
    const token = loadToken();
    const q = token ? `?token=${encodeURIComponent(token)}` : '';
    return `${protocol}://${host}/ws/terminal${q}`;
  }

  function connectWS() {
    if (ws && (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING)) return;
    const url = buildWsUrl();
    term.writeln('\x1b[90m*** Connecting to terminal... ' + url + ' ***\x1b[0m');
    try {
      ws = new WebSocket(url);

      ws.addEventListener('open', () => {
        term.writeln('\x1b[32m*** Connected ***\x1b[0m');
        if (reconnectTimer) { clearTimeout(reconnectTimer); reconnectTimer = null; }
        sendResize();
      });

      ws.addEventListener('message', (evt) => {
        // Server sends plain text fragments (escape sequences included)
        term.write(evt.data);
      });

      ws.addEventListener('close', (ev) => {
        term.writeln('\r\n\x1b[31m*** Connection closed. Reconnecting... ***\x1b[0m\r\n');
        scheduleReconnect();
      });

      ws.addEventListener('error', (ev) => {
        console.warn('WS error', ev);
        // Let close handler deal with reconnect
      });
    } catch (e) {
      term.writeln('\x1b[31m*** WebSocket connect failed: ' + e.message + ' ***\x1b[0m');
      scheduleReconnect();
    }
  }

  function scheduleReconnect() {
    if (reconnectTimer) return;
    reconnectTimer = setTimeout(() => {
      reconnectTimer = null;
      connectWS();
    }, RECONNECT_MS);
  }

  function reconnectWS() {
    try {
      if (ws) ws.close();
    } catch(e){}
    ws = null;
    connectWS();
  }

  // Map xterm input -> WS
  term.onData(data => {
    if (!ws || ws.readyState !== WebSocket.OPEN) return;
    const msg = JSON.stringify({ type: 'input', data });
    ws.send(msg);
  });

  // Helper: send Ctrl-C
  function sendCtrlC() {
    if (!ws || ws.readyState !== WebSocket.OPEN) {
      term.writeln('\x1b[33m*** Not connected ***\x1b[0m');
      return;
    }
    // Ctrl-C is 0x03
    const msg = JSON.stringify({ type: 'input', data: '\x03' });
    ws.send(msg);
  }

  // Kick off initial connection
  connectWS();

  // expose small debug helpers if needed
  window.auroraTerminal = {
    reconnect: reconnectWS,
    sendCtrlC,
    setToken: (t) => { saveToken(t); },
    getToken: () => loadToken(),
  };
})();
