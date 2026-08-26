const WS_BASE = import.meta.env.VITE_WS_BASE_URL || 'ws://127.0.0.1:8000/api/v1';

/**
 * Opens a WebSocket connection for a recovery stream.
 * Returns an object with { socket, close }.
 * @param {string} transactionId
 * @param {function} onEvent - called with parsed event object
 * @param {function} onError - called on error
 * @param {function} onClose - called on close
 */
export function connectRecoveryStream(transactionId, { onEvent, onError, onClose }) {
  const url = `${WS_BASE}/ws/recovery/${transactionId}`;
  const socket = new WebSocket(url);

  socket.onopen = () => {
    /* connection established */
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
