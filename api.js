// src/lib/api.js
//
// Thin fetch wrapper for every /api/* route in api_server.py. Every call
// attaches X-Init-Data (verified server-side) and X-Username (display
// hint only, never trusted for authorization - see api_server.py).

import { getInitData, getInitDataUnsafe } from './telegram';

const BASE_URL = ''; // same-origin: API server and Mini App are served
                      // from the same host/deployment (one-host setup)

async function call(method, path, body) {
  const initData = getInitData();
  const username = getInitDataUnsafe()?.user?.username || '';

  const res = await fetch(`${BASE_URL}/api${path}`, {
    method,
    headers: {
      'Content-Type': 'application/json',
      'X-Init-Data': initData,
      'X-Username': username,
    },
    body: body ? JSON.stringify(body) : undefined,
  });

  const data = await res.json().catch(() => ({}));

  if (!res.ok) {
    // api_server.py raises HTTPException(400, detail=result) for
    // handler-level failures, and 401 with {detail: "..."} for auth
    // failures - normalize both into a thrown Error the UI can catch.
    const detail = data.detail || data;
    const message = typeof detail === 'object' ? (detail.message || detail.error || 'Request failed') : detail;
    const err = new Error(message);
    err.status = res.status;
    err.body = detail;
    throw err;
  }

  return data;
}

export const api = {
  bootstrap: () => call('GET', '/bootstrap'),
  setPhone: (phone) => call('POST', '/set-phone', { phone }),
  setLanguage: (language) => call('POST', '/set-language', { language }),

  getRooms: () => call('GET', '/rooms'),
  getRoomCards: (roomFee) => call('GET', `/rooms/${roomFee}/cards`),
  buyCards: (roomFee, cardIndices) => call('POST', '/buy-cards', { room_fee: roomFee, card_indices: cardIndices }),

  getGameState: (gameId) => call('GET', `/games/${gameId}/state`),
  toggleAutoWin: (gameId, enabled) => call('POST', '/toggle-auto-win', { game_id: gameId, enabled }),
  markNumber: (gameId, cardIndex, number) => call('POST', '/mark-number', { game_id: gameId, card_index: cardIndex, number }),
  claimBingo: (gameId) => call('POST', '/claim-bingo', { game_id: gameId }),

  getDepositAccount: () => call('GET', '/deposit-account'),
  submitDepositSms: (smsText, expectedAmount) => call('POST', '/submit-deposit-sms', { sms_text: smsText, expected_amount: expectedAmount }),
  withdraw: (amount) => call('POST', '/withdraw', { amount }),
  transfer: (toUsername, amount) => call('POST', '/transfer', { to_username: toUsername, amount }),

  getProfile: () => call('GET', '/profile'),
  getTransactions: (limit = 20) => call('GET', `/transactions?limit=${limit}`),
  getReferral: () => call('GET', '/referral'),
  claimDailyBonus: () => call('POST', '/daily-bonus'),
};
