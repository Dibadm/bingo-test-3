import { useState, useEffect, useCallback, useRef } from 'react';
import { useSearchParams } from 'react-router-dom';
import { api } from '../lib/api';
import { haptic, hapticNotification, tg } from '../lib/telegram';
import type { RoomState, CardOwnership } from '../types';

const TOTAL_CARDS = 200;
const PER_PAGE = 50;
const TOTAL_PAGES = TOTAL_CARDS / PER_PAGE;

const styles: Record<string, React.CSSProperties> = {
  root: {
    display: 'flex',
    flexDirection: 'column',
    height: '100vh',
    background: 'var(--tg-theme-bg-color, #1a1a2e)',
    color: 'var(--tg-theme-text-color, #eee)',
    userSelect: 'none',
  },
  header: {
    padding: '10px 14px 6px',
    background: 'rgba(255,255,255,0.05)',
    borderBottom: '1px solid rgba(255,255,255,0.08)',
  },
  title: { fontSize: 15, fontWeight: 700, color: '#FFD700' },
  stats: { fontSize: 12, opacity: 0.75, marginTop: 3 },
  countdown: {
    display: 'inline-block', marginLeft: 8,
    background: '#e74c3c', color: '#fff',
    borderRadius: 4, padding: '1px 6px',
    fontSize: 12, fontWeight: 700,
  },
  grid: {
    flex: 1,
    overflowY: 'auto',
    padding: '10px 8px',
    display: 'grid',
    gridTemplateColumns: 'repeat(10, 1fr)',
    gap: 4,
    alignContent: 'start',
  },
  card: (state: 'mine' | 'taken' | 'free') => ({
    aspectRatio: '1',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    borderRadius: 5,
    fontSize: 11,
    fontWeight: 600,
    cursor: state === 'taken' ? 'default' : 'pointer',
    transition: 'transform 0.1s, box-shadow 0.1s',
    background:
      state === 'mine'
        ? 'linear-gradient(135deg, #27ae60, #1abc9c)'
        : state === 'taken'
        ? 'rgba(255,255,255,0.08)'
        : 'rgba(255,255,255,0.12)',
    color:
      state === 'taken' ? 'rgba(255,255,255,0.3)' : '#fff',
    boxShadow:
      state === 'mine' ? '0 2px 8px rgba(39,174,96,0.5)' : 'none',
    border:
      state === 'mine'
        ? '1.5px solid #2ecc71'
        : '1.5px solid rgba(255,255,255,0.1)',
  }),
  footer: {
    padding: '8px 12px',
    background: 'rgba(0,0,0,0.3)',
    borderTop: '1px solid rgba(255,255,255,0.08)',
  },
  pagination: {
    display: 'flex',
    justifyContent: 'center',
    gap: 8,
    marginBottom: 8,
  },
  pageBtn: (active: boolean): React.CSSProperties => ({
    width: 32, height: 32,
    borderRadius: '50%',
    border: 'none',
    cursor: 'pointer',
    fontWeight: 700, fontSize: 13,
    background: active ? '#FFD700' : 'rgba(255,255,255,0.12)',
    color: active ? '#000' : '#fff',
  }),
  actions: { display: 'flex', gap: 8 },
  btn: (variant: 'primary' | 'secondary' | 'success'): React.CSSProperties => ({
    flex: variant === 'primary' ? 2 : 1,
    padding: '10px 4px',
    borderRadius: 8, border: 'none',
    cursor: 'pointer', fontWeight: 700, fontSize: 13,
    background:
      variant === 'success'
        ? 'linear-gradient(135deg, #27ae60, #1abc9c)'
        : variant === 'primary'
        ? 'linear-gradient(135deg, #3498db, #9b59b6)'
        : 'rgba(255,255,255,0.12)',
    color: '#fff',
  }),
  legend: {
    display: 'flex', gap: 12, fontSize: 11,
    opacity: 0.7, marginBottom: 6,
  },
  dot: (color: string): React.CSSProperties => ({
    width: 10, height: 10, borderRadius: 2,
    background: color, display: 'inline-block', marginRight: 3,
  }),
};

export default function CardSelection() {
  const [params] = useSearchParams();
  const fee = Number(params.get('room') ?? '10');

  const [page, setPage] = useState(0);
  const [roomState, setRoomState] = useState<RoomState | null>(null);
  const [cards, setCards] = useState<CardOwnership[]>([]);
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [loading, setLoading] = useState(false);
  const pollRef = useRef<ReturnType<typeof setInterval>>();

  const fetchState = useCallback(async () => {
    const [rs, rc] = await Promise.all([
      api.getRoomState(fee),
      api.getRoomCards(fee),
    ]);
    if (rs.ok && rs.data) setRoomState(rs.data);
    if (rc.ok && rc.data) setCards(rc.data);
  }, [fee]);

  useEffect(() => {
    fetchState();
    pollRef.current = setInterval(fetchState, 3000);
    return () => clearInterval(pollRef.current);
  }, [fetchState]);

  // Set up Telegram Back Button
  useEffect(() => {
    tg?.BackButton?.show();
    const fn = () => tg?.close();
    tg?.BackButton?.onClick(fn);
    return () => {
      tg?.BackButton?.offClick(fn);
      tg?.BackButton?.hide();
    };
  }, []);

  const cardMap = new Map(cards.map(c => [c.card_number, c]));

  function getState(n: number): 'mine' | 'taken' | 'free' {
    if (selected.has(n)) return 'mine';
    const c = cardMap.get(n);
    if (c?.owned_by_me) return 'mine';
    if (c?.taken) return 'taken';
    return 'free';
  }

  function toggleCard(n: number) {
    const state = getState(n);
    if (state === 'taken') return;
    haptic('light');
    setSelected(prev => {
      const next = new Set(prev);
      if (next.has(n)) {
        next.delete(n);
      } else {
        if (next.size >= 5) {
          tg?.showAlert('You can select up to 5 cards per game.');
          return prev;
        }
        next.add(n);
      }
      return next;
    });
  }

  function randomPick(n: number) {
    const free = [];
    for (let i = 1; i <= TOTAL_CARDS; i++) {
      if (getState(i) === 'free' && !selected.has(i)) free.push(i);
    }
    const picks = free.sort(() => Math.random() - 0.5).slice(0, n);
    setSelected(prev => {
      const next = new Set(prev);
      for (const p of picks) {
        if (next.size < 5) next.add(p);
      }
      return next;
    });
    haptic('medium');
  }

  async function handleBuy() {
    if (selected.size === 0) {
      tg?.showAlert('Please select at least 1 card.');
      return;
    }
    setLoading(true);
    const res = await api.buyCards(fee, Array.from(selected));
    setLoading(false);
    if (res.ok && res.data?.success) {
      hapticNotification('success');
      setSelected(new Set());
      tg?.showAlert(res.data.message ?? 'Cards purchased!');
      fetchState();
    } else {
      hapticNotification('error');
      tg?.showAlert(res.data?.message ?? res.error ?? 'Purchase failed.');
    }
  }

  const pageStart = page * PER_PAGE + 1;
  const pageEnd = Math.min(pageStart + PER_PAGE - 1, TOTAL_CARDS);
  const pool = roomState ? Math.round(roomState.prize_pool * 0.8) : 0;
  const cost = selected.size * fee;

  return (
    <div style={styles.root}>
      {/* Header */}
      <div style={styles.header}>
        <div style={styles.title}>
          🎯 {fee} ETB Room
          {roomState?.status === 'countdown' && (
            <span style={styles.countdown}>⏱ {roomState.countdown_remaining}s</span>
          )}
        </div>
        <div style={styles.stats}>
          🏆 Prize: <b>{pool} ETB</b> &nbsp;|&nbsp;
          📦 Sold: <b>{roomState?.cards_sold ?? 0}/200</b> &nbsp;|&nbsp;
          👤 Last: <b>{roomState?.last_buyer_name ?? '—'}</b>
        </div>
        {/* Legend */}
        <div style={styles.legend}>
          <span><span style={styles.dot('#27ae60')} />Mine</span>
          <span><span style={styles.dot('rgba(255,255,255,0.08)')} />Taken</span>
          <span><span style={styles.dot('rgba(255,255,255,0.18)')} />Free</span>
        </div>
      </div>

      {/* Card grid */}
      <div style={styles.grid}>
        {Array.from({ length: pageEnd - pageStart + 1 }, (_, i) => {
          const n = pageStart + i;
          const st = getState(n);
          return (
            <div
              key={n}
              style={styles.card(st)}
              onClick={() => toggleCard(n)}
            >
              {st === 'mine' ? `✓${n}` : n}
            </div>
          );
        })}
      </div>

      {/* Footer */}
      <div style={styles.footer}>
        {/* Pagination */}
        <div style={styles.pagination}>
          {Array.from({ length: TOTAL_PAGES }, (_, i) => (
            <button
              key={i}
              style={styles.pageBtn(i === page)}
              onClick={() => { setPage(i); haptic('light'); }}
            >
              {i + 1}
            </button>
          ))}
        </div>

        {/* Actions */}
        <div style={styles.actions}>
          <button style={styles.btn('secondary')} onClick={() => randomPick(1)}>🎲 ×1</button>
          <button style={styles.btn('secondary')} onClick={() => randomPick(2)}>🎲 ×2</button>
          {selected.size > 0 ? (
            <button
              style={styles.btn('success')}
              onClick={handleBuy}
              disabled={loading}
            >
              {loading ? '⏳ Buying…' : `▶ BUY (${selected.size}×${fee}=${cost} ETB)`}
            </button>
          ) : (
            <button style={{ ...styles.btn('primary'), opacity: 0.5 }} disabled>
              Select cards above
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
