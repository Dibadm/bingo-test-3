import { getInitData, getInitDataUnsafe } from './telegram';

const BASE_URL = import.meta.env.VITE_API_URL ?? '';

async function call<T>(method: string, path: string, body?: unknown): Promise<T> {
  const initData = getInitData();
  const username = getInitDataUnsafe()?.user?.username ?? '';

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
    const detail = data.detail ?? data;
    const message =
      typeof detail === 'object'
        ? detail.message ?? detail.error ?? 'Request failed'
        : String(detail);
    const err = new Error(message) as Error & { status: number; body: unknown };
    err.status = res.status;
    err.body = detail;
    throw err;
  }

  return data as T;
}

export const api = {
  bootstrap: ()                         => call<{ user: any }>('GET', '/bootstrap'),
  setPhone:  (phone: string)            => call('POST', '/set-phone', { phone }),
  setLanguage:(language: string)        => call('POST', '/set-language', { language }),

  getRooms:    ()                       => call<{ rooms: any[] }>('GET', '/rooms'),
  getRoomCards:(roomFee: number)        => call<any>('GET', `/rooms/${roomFee}/cards`),
  buyCards:    (roomFee: number, cardIndices: number[]) =>
    call<any>('POST', '/buy-cards', { room_fee: roomFee, card_indices: cardIndices }),

  getGameState: (gameId: number)        => call<any>('GET', `/games/${gameId}/state`),
  toggleAutoWin:(gameId: number, enabled: boolean) =>
    call('POST', '/toggle-auto-win', { game_id: gameId, enabled }),
  claimBingo:  (gameId: number)         => call<any>('POST', '/claim-bingo', { game_id: gameId }),

  getDepositAccount: ()                 => call<any>('GET', '/deposit-account'),
  submitDepositSms: (smsText: string, expectedAmount?: number) =>
    call<any>('POST', '/submit-deposit-sms', { sms_text: smsText, expected_amount: expectedAmount }),
  withdraw: (amount: number)            => call<any>('POST', '/withdraw', { amount }),
  transfer: (toUsername: string, amount: number) =>
    call<any>('POST', '/transfer', { to_username: toUsername, amount }),

  getProfile:      ()                   => call<any>('GET', '/profile'),
  getTransactions: (limit = 20)         => call<any>('GET', `/transactions?limit=${limit}`),
  getReferral:     ()                   => call<any>('GET', '/referral'),
  claimDailyBonus: ()                   => call<any>('POST', '/daily-bonus'),
};
