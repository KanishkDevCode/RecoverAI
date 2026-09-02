const WS_BASE = import.meta.env.VITE_WS_URL || 'ws://127.0.0.1:8000/api/v1';

/**
 * Opens a WebSocket connection for a recovery stream.
 * Returns an object with { socket, close }.
 * @param {string} transactionId
 * @param {function} onEvent - called with parsed event object
 * @param {function} onError - called on error
 * @param {function} onClose - called on close
 */
export function connectRecoveryStream(transactionId, { onOpen, onEvent, onError, onClose }) {
  const apiKey = 'test_secret_key_123'; // Using same default key as api.js
  const url = `${WS_BASE}/ws/recovery/${transactionId}?api_key=${apiKey}`;
  const socket = new WebSocket(url);

  socket.onopen = () => {
    if (onOpen) onOpen();
  };

  socket.onmessage = (msg) => {
    try {
      const event = JSON.parse(msg.data);
      onEvent(event);
    } catch (e) {
      if (onError) onError(e);
    }
  };

  socket.onerror = (e) => {
    if (onError) onError(e);
  };

  socket.onclose = () => {
    if (onClose) onClose();
  };

  return {
    socket,
    close: () => socket.close(),
  };
}
