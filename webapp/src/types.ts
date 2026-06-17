export interface RoomState {
  game_id: number | null;
  status: 'lobby' | 'countdown' | 'running' | 'finished';
  cards_sold: number;
  prize_pool: number;
  countdown_remaining: number;
  last_buyer_name: string;
}

export interface CardOwnership {
  card_number: number;
  owned_by_me: boolean;
  taken: boolean;
}

export interface GameState {
  game_id: number;
  status: 'running' | 'finished';
  called_numbers: number[];
  prize_pool: number;
  players: number;
  my_cards: CardData[];
}

export interface CardData {
  card_number: number;
  grid: number[][];
  is_winner: boolean;
  win_type: string;
}

export interface ApiResponse<T> {
  ok: boolean;
  data?: T;
  error?: string;
}
