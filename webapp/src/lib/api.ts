import { getInitData } from './telegram';
import type { RoomState, CardOwnership, GameState, ApiResponse } from '../types';

const BASE_URL = import.meta.env.VITE_API_URL ?? '';

async function request<T>(
  path: string,
  options: RequestInit = {}
): Promise<ApiResponse<T>> {
  const initData = getInitData();
  const res = await fetch(`${BASE_URL}${path}`, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      'X-Telegram-Init-Data': initData,
      ...options.headers,
    },
  });
  if (!res.ok) {
    const text = await res.text();
    return { ok: false, error: text };
  }
  const json = await res.json();
  return { ok: true, data: json };
}

export const api = {
  getRoomState: (fee: number) =>
    request<RoomState>(`/api/room/${fee}/state`),

  getRoomCards: (fee: number) =>
    request<CardOwnership[]>(`/api/room/${fee}/cards`),

  buyCards: (fee: number, cardNumbers: number[]) =>
    request<{ success: boolean; message: string }>(`/api/room/${fee}/buy`, {
      method: 'POST',
      body: JSON.stringify({ card_numbers: cardNumbers }),
    }),

  getGameState: (gameId: number) =>
    request<GameState>(`/api/game/${gameId}/state`),

  claimBingo: (gameId: number) =>
    request<{ won: boolean; prize?: number }>(`/api/game/${gameId}/bingo`, {
      method: 'POST',
      body: JSON.stringify({}),
    }),
};
