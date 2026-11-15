// The WebSocket to the tutor. Text messages are JSON events; binary messages are the tutor's voice, one sentence each.
// When the connection drops, it reconnects every 1.5 seconds.

let socket = null;

const isOpen = () => socket && socket.readyState === WebSocket.OPEN;

/** Send one event to the tutor, such as send('text', {text: 'مرحبا'}). False when not connected. */
export function send(type, fields = {}) {
  if (!isOpen()) return false;
  socket.send(JSON.stringify({type, ...fields}));
  return true;
}

/** Send a chunk of microphone audio (16 kHz 16-bit mono PCM). */
export function sendAudio(pcm) {
  if (isOpen()) socket.send(pcm);
}

export function connect(handlers) {
  const scheme = location.protocol === 'https:' ? 'wss://' : 'ws://';
  socket = new WebSocket(scheme + location.host + '/ws');
  socket.binaryType = 'arraybuffer';
  socket.onopen = handlers.onOpen;
  socket.onclose = () => {
    handlers.onClose();   // a 401 while reconnecting means the login has expired; the health check notices
    setTimeout(() => connect(handlers), 1500);
  };
  socket.onmessage = e => {
    if (typeof e.data === 'string') handlers.onEvent(JSON.parse(e.data));
    else handlers.onAudio(e.data);
  };
}
