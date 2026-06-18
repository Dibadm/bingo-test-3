export interface User {
  telegram_id: number;
  username: string;
  first_name: string;
  phone: string;
  balance: number;
  language: 'en' | 'am';
  referral_code: string;
}

export interface Room {
  room_fee: number;
  state: 'lobby' | 'countdown' | 'running';
  pool: number;
  cards_sold: number;
  card_pool_size: number;
  player_count: number;
}

export interface RoomCards {
  state: 'lobby' | 'countdown' | 'running';
  game_id: number | null;
  pool: number;
  cards_sold: number;
  card_pool_size: number;
  max_cards_per_player: number;
  taken_cards: number[];
  my_cards: number[];
}

export interface LastCall {
  letter: string;
  number: number;
  amharic: string;
}

export interface GameCard {
  card_index: number;
  card_number: number;
  grid: number[][];
  called: number[];
}

export interface GameState {
  state: 'waiting' | 'running' | 'finished';
  room_fee: number;
  pool: number;
  call_count: number;
  max_calls: number;
  called_numbers: number[];
  last_call: LastCall | null;
  player_count: number;
  auto_win: boolean;
  my_cards: GameCard[];
  i_won: boolean;
  winners: number[];
  per_winner_amount: number;
}
