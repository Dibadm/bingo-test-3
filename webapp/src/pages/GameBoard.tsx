// @ts-nocheck
import { useState, useEffect, useRef, useCallback } from 'react';
import { useSearchParams } from 'react-router-dom';
import { api } from '../lib/api';
import { haptic, hapticNotification, tg } from '../lib/telegram';
import type { GameState, CardData } from '../types';

const BINGO_COLS = ['B', 'I', 'N', 'G', 'O'];
const COL_RANGES = [
  [1, 15], [16, 30], [31, 45], [46, 60], [61, 75],
] as const;

function getColLetter(n: number): string {
  for (let i = 0; i < COL_RANGES.length; i++) {
    const [lo, hi] = COL_RANGES[i];
    if (n >= lo && n <= hi) return BINGO_COLS[i];
  }
  return '';
}

const CSS = `
  @keyframes pop {
    0%   { transform: scale(1); }
    50%  { transform: scale(1.4); }
    100% { transform: scale(1); }
  }
  @keyframes pulse {
    0%, 100% { opacity: 1; }
    50%       { opacity: 0.6; }
  }
  .cell-called { animation: pop 0.3s ease; }
  .bingo-btn   { animation: pulse 1s infinite; }
`;

export default function GameBoard() {
  const [params] = useSearchParams();
  const gameId = Number(params.get('game_id') ?? '0');

  const [gameState, setGameState] = useState<GameState | null>(null);
  const [prevCalled, setPrevCalled] = useState<Set<number>>(new Set());
  const [newlyCalledCell, setNewlyCalledCell] = useState<number | null>(null);
  const [hasWin, setHasWin] = useState(false);
  const [claimResult, setClaimResult] = useState<string | null>(null);
  const pollRef = useRef<any>();

  const fetchState = useCallback(async () => {
    const res = await api.getGameState(gameId);
    if (!res.ok || !res.data) return;
    const gs = res.data;
    setGameState(prev => {
      if (prev) {
        const newNums = gs.called_numbers.filter(n => !prev.called_numbers.includes(n));
        if (newNums.length > 0) {
          setNewlyCalledCell(newNums[newNums.length - 1]);
          setTimeout(() => setNewlyCalledCell(null), 600);
          haptic('light');
        }
      }
      setPrevCalled(new Set(prev?.called_numbers ?? []));
      return gs;
    });

    const calledSet = new Set(gs.called_numbers);
    const win = gs.my_cards.some(card => checkWin(card.grid, calledSet));
    setHasWin(win);
  }, [gameId]);

  useEffect(() => {
    fetchState();
    pollRef.current = setInterval(fetchState, 2500);
    return () => clearInterval(pollRef.current);
  }, [fetchState]);

  useEffect(() => {
    tg?.BackButton?.show();
    const fn = () => tg?.close();
    tg?.BackButton?.onClick(fn);
    return () => { tg?.BackButton?.offClick(fn); tg?.BackButton?.hide(); };
  }, []);

  async function claimBingo() {
    haptic('heavy');
    const res = await api.claimBingo(gameId);
    if (res.ok && res.data?.won) {
      hapticNotification('success');
      setClaimResult(`🏆 WINNER! +${res.data.prize} ETB`);
    } else {
      hapticNotification('error');
      setClaimResult('❌ Not a winning pattern yet. Keep playing!');
      setTimeout(() => setClaimResult(null), 2500);
    }
  }

  if (!gameState) {
    return (
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100vh' }}>
        <div style={{ textAlign: 'center', opacity: 0.7 }}>
          <div style={{ fontSize: 40 }}>🎯</div>
          <div>Loading game…</div>
        </div>
      </div>
    );
  }

  const calledSet = new Set(gameState.called_numbers);
  const lastNum = gameState.called_numbers[gameState.called_numbers.length - 1];

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100vh', overflow: 'hidden' }}>
      <style>{CSS}</style>

      {/* Top bar */}
      <div style={{
        padding: '8px 12px',
        background: 'rgba(255,255,255,0.05)',
        borderBottom: '1px solid rgba(255,255,255,0.08)',
        display: 'flex', justifyContent: 'space-between', alignItems: 'center',
      }}>
        <div>
          <div style={{ fontSize: 13, fontWeight: 700, color: '#FFD700' }}>
            🏆 {Math.round(gameState.prize_pool * 0.8)} ETB Pool
          </div>
          <div style={{ fontSize: 11, opacity: 0.7 }}>
            {gameState.players} players · {gameState.called_numbers.length}/75 called
          </div>
        </div>
        {lastNum && (
          <div style={{
            width: 52, height: 52,
            borderRadius: '50%',
            background: 'linear-gradient(135deg, #e74c3c, #c0392b)',
            display: 'flex', flexDirection: 'column',
            alignItems: 'center', justifyContent: 'center',
            fontWeight: 900, boxShadow: '0 3px 12px rgba(231,76,60,0.5)',
          }}>
            <div style={{ fontSize: 9, letterSpacing: 1, color: 'rgba(255,255,255,0.7)' }}>
              {getColLetter(lastNum)}
            </div>
            <div style={{ fontSize: 18, color: '#fff', lineHeight: 1 }}>{lastNum}</div>
          </div>
        )}
      </div>

      {/* Number grid 1–75 */}
      <div style={{ padding: '6px 8px' }}>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(15, 1fr)', gap: 2, marginBottom: 3 }}>
          {BINGO_COLS.map(l => (
            <div key={l} style={{
              textAlign: 'center', fontSize: 10, fontWeight: 700,
              color: '#FFD700', gridColumn: `span 3`,
            }}>{l}</div>
          ))}
        </div>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(15, 1fr)', gap: 2 }}>
          {Array.from({ length: 75 }, (_, i) => {
            const n = i + 1;
            const called = calledSet.has(n);
            const isNew = n === newlyCalledCell;
            return (
              <div
                key={n}
                className={isNew ? 'cell-called' : undefined}
                style={{
                  aspectRatio: '1',
                  borderRadius: 4,
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                  fontSize: 9, fontWeight: called ? 700 : 400,
                  background: called
                    ? 'linear-gradient(135deg, #e74c3c, #c0392b)'
                    : 'rgba(255,255,255,0.08)',
                  color: called ? '#fff' : 'rgba(255,255,255,0.45)',
                  boxShadow: called ? '0 1px 4px rgba(231,76,60,0.4)' : 'none',
                }}
              >
                {n}
              </div>
            );
          })}
        </div>
      </div>

      {/* User's cards */}
      <div style={{ flex: 1, overflowY: 'auto', padding: '4px 8px' }}>
        <div style={{ fontSize: 12, fontWeight: 700, marginBottom: 6, opacity: 0.8 }}>
          🃏 My Cards ({gameState.my_cards.length})
        </div>
        {gameState.my_cards.map(card => (
          <BingoCard key={card.card_number} card={card} calledSet={calledSet} />
        ))}
      </div>

      {/* BINGO button */}
      <div style={{ padding: '8px 12px', background: 'rgba(0,0,0,0.3)' }}>
        {claimResult ? (
          <div style={{
            textAlign: 'center', padding: '10px',
            borderRadius: 10, background: 'rgba(255,255,255,0.1)',
            fontWeight: 700, fontSize: 14,
          }}>{claimResult}</div>
        ) : (
          <button
            className={hasWin ? 'bingo-btn' : undefined}
            onClick={claimBingo}
            style={{
              width: '100%', padding: '12px',
              borderRadius: 12, border: 'none',
              fontWeight: 900, fontSize: 18, cursor: 'pointer',
              background: hasWin
                ? 'linear-gradient(135deg, #f39c12, #e74c3c)'
                : 'rgba(255,255,255,0.15)',
              color: hasWin ? '#fff' : 'rgba(255,255,255,0.5)',
              boxShadow: hasWin ? '0 4px 20px rgba(231,76,60,0.6)' : 'none',
              letterSpacing: 2,
            }}
          >
            🎉 BINGO!
          </button>
        )}
      </div>
    </div>
  );
}

function checkWin(grid: number[][], called: Set<number>): boolean {
  const marked = grid.map(row => row.map(n => n === 0 || called.has(n)));
  if (marked.some(row => row.every(Boolean))) return true;
  for (let c = 0; c < 5; c++) {
    if (marked.every(row => row[c])) return true;
  }
  if ([0,1,2,3,4].every(i => marked[i][i])) return true;
  if ([0,1,2,3,4].every(i => marked[i][4-i])) return true;
  if (marked[0][0] && marked[0][4] && marked[4][0] && marked[4][4]) return true;
  return false;
}

function BingoCard({ card, calledSet }: { card: any; calledSet: Set<number> }) {
  return (
    <div style={{
      marginBottom: 10, borderRadius: 10,
      background: card.is_winner
        ? 'linear-gradient(135deg, rgba(39,174,96,0.25), rgba(26,188,156,0.2))'
        : 'rgba(255,255,255,0.05)',
      border: card.is_winner
        ? '1.5px solid #27ae60'
        : '1px solid rgba(255,255,255,0.1)',
      overflow: 'hidden',
    }}>
      <div style={{
        display: 'flex', justifyContent: 'space-between',
        padding: '5px 10px',
        background: 'rgba(255,255,255,0.04)',
        fontSize: 11, fontWeight: 700,
      }}>
        <span>Card #{card.card_number}</span>
        {card.is_winner && (
          <span style={{ color: '#27ae60' }}>🏆 {card.win_type}</span>
        )}
      </div>
      <div style={{
        display: 'grid', gridTemplateColumns: 'repeat(5, 1fr)',
        gap: 2, padding: '4px 6px 0',
      }}>
        {BINGO_COLS.map(l => (
          <div key={l} style={{
            textAlign: 'center', fontSize: 11, fontWeight: 700, color: '#FFD700',
          }}>{l}</div>
        ))}
      </div>
      <div style={{
        display: 'grid', gridTemplateColumns: 'repeat(5, 1fr)',
        gap: 3, padding: '3px 6px 6px',
      }}>
        {card.grid.flat().map((n, idx) => {
          const isCenter = idx === 12;
          const isMarked = n === 0 || calledSet.has(n);
          return (
            <div key={idx} style={{
              aspectRatio: '1',
              borderRadius: 5,
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              fontSize: 12, fontWeight: isMarked ? 700 : 400,
              background: isCenter
                ? 'linear-gradient(135deg, #f39c12, #e67e22)'
                : isMarked
                ? 'linear-gradient(135deg, #27ae60, #1abc9c)'
                : 'rgba(255,255,255,0.08)',
              color: isMarked ? '#fff' : 'rgba(255,255,255,0.55)',
              boxShadow: isMarked && !isCenter ? '0 1px 4px rgba(39,174,96,0.4)' : 'none',
            }}>
              {isCenter ? '★' : n}
            </div>
          );
        })}
      </div>
    </div>
  );
}
