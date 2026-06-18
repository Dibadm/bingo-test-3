import { useEffect, useState, useCallback } from 'react';
import { useStore } from '../lib/store';
import { api } from '../lib/api';
import { fmt } from '../components/Chrome';
import { haptic, mainButton, showAlert } from '../lib/telegram';
import type { RoomCards } from '../types';

export default function CardSelectScreen({
  roomFee,
  onBack,
  onGameStart,
}: {
  roomFee: number;
  onBack: () => void;
  onGameStart: (gameId: number) => void;
}) {
  const { user, runAction, refreshUser } = useStore();
  const [data, setData] = useState<RoomCards | null>(null);
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [buying, setBuying] = useState(false);

  const load = useCallback(async () => {
    const res = await runAction(() => api.getRoomCards(roomFee));
    setData(res);
    if (res.state === 'running' && res.game_id) {
      onGameStart(res.game_id);
    }
    return res;
  }, [roomFee]);

  useEffect(() => {
    load();
    const interval = setInterval(load, 2500);
    return () => clearInterval(interval);
  }, [load]);

  const toggle = (idx: number) => {
    if (!data) return;
    if (data.taken_cards.includes(idx) || data.my_cards.includes(idx)) return;
    setSelected(prev => {
      const next = new Set(prev);
      if (next.has(idx)) {
        next.delete(idx);
      } else {
        if (next.size + data.my_cards.length >= data.max_cards_per_player) {
          showAlert(`You can hold at most ${data.max_cards_per_player} cards per round.`);
          return prev;
        }
        next.add(idx);
      }
      return next;
    });
    haptic.light();
  };

  const randomPick = (count: number) => {
    if (!data) return;
    const taken = new Set([...data.taken_cards, ...data.my_cards, ...selected]);
    const available: number[] = [];
    for (let i = 0; i < data.card_pool_size; i++) {
      if (!taken.has(i)) available.push(i);
    }
    available.sort(() => Math.random() - 0.5);
    const roomLeft = data.max_cards_per_player - data.my_cards.length - selected.size;
    const toAdd = available.slice(0, Math.min(count, roomLeft));
    if (toAdd.length === 0) {
      showAlert(`You can hold at most ${data.max_cards_per_player} cards per round.`);
      return;
    }
    setSelected(prev => new Set([...prev, ...toAdd]));
    haptic.medium();
  };

  const confirmPurchase = useCallback(async () => {
    if (selected.size === 0) return;
    setBuying(true);
    try {
      await runAction(() => api.buyCards(roomFee, [...selected]));
      haptic.success();
      setSelected(new Set());
      await refreshUser();
      const fresh = await load();
      if (fresh.state === 'running' && fresh.game_id) onGameStart(fresh.game_id);
    } catch {
      await load();
    } finally {
      setBuying(false);
    }
  }, [selected, roomFee]);

  useEffect(() => {
    if (!data) return;
    const cost = selected.size * roomFee;
    if (selected.size === 0) {
      mainButton.hide();
      return;
    }
    mainButton.show(
      `Buy ${selected.size} card${selected.size > 1 ? 's' : ''} — ${fmt(cost)} ETB`,
      confirmPurchase
    );
    return () => mainButton.offClick(confirmPurchase);
  }, [data, selected, roomFee, confirmPurchase]);

  if (!data) {
    return <div className="screen"><div className="card" style={{ textAlign: 'center' }}>Loading…</div></div>;
  }

  return (
    <div className="screen">
      <div className="row">
        <button className="btn btn-secondary" onClick={onBack} style={{ padding: '8px 14px' }}>← Back</button>
        <div style={{ fontWeight: 700 }}>Bingo {fmt(roomFee)} ETB</div>
        <div className="pill pill-gold">💰 {fmt(user?.balance)} ETB</div>
      </div>

      <div className="card">
        <div className="row">
          <span style={{ fontSize: 13, color: 'var(--text-dim)' }}>Prize Pool</span>
          <span style={{ fontWeight: 700, color: 'var(--gold-bright)' }}>{fmt(data.pool)} ETB</span>
        </div>
        <div className="row">
          <span style={{ fontSize: 13, color: 'var(--text-dim)' }}>Cards sold</span>
          <span>{data.cards_sold}/{data.card_pool_size}</span>
        </div>
        {data.state === 'countdown' && (
          <div style={{ marginTop: 8, textAlign: 'center', color: 'var(--gold-bright)', fontWeight: 700 }}>
            ⏱ Game starting soon!
          </div>
        )}
      </div>

      {data.my_cards.length > 0 && (
        <div className="pill pill-gold" style={{ alignSelf: 'flex-start' }}>
          ✅ You hold {data.my_cards.length} card{data.my_cards.length > 1 ? 's' : ''} this round
        </div>
      )}

      <div style={{ display: 'flex', gap: 8 }}>
        <button className="btn btn-secondary" style={{ flex: 1 }} onClick={() => randomPick(1)}>🎲 Random ×1</button>
        <button className="btn btn-secondary" style={{ flex: 1 }} onClick={() => randomPick(2)}>🎲 Random ×2</button>
      </div>

      <CardGrid
        poolSize={data.card_pool_size}
        taken={data.taken_cards}
        mine={data.my_cards}
        selected={selected}
        onToggle={toggle}
      />

      {buying && (
        <div style={{ textAlign: 'center', color: 'var(--text-dim)', fontSize: 13 }}>Processing purchase…</div>
      )}
    </div>
  );
}

function CardGrid({
  poolSize, taken, mine, selected, onToggle,
}: {
  poolSize: number; taken: number[]; mine: number[];
  selected: Set<number>; onToggle: (i: number) => void;
}) {
  const takenSet = new Set(taken);
  const mineSet = new Set(mine);

  return (
    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(10, 1fr)', gap: 5 }}>
      {Array.from({ length: poolSize }, (_, i) => {
        const isTaken = takenSet.has(i);
        const isMine = mineSet.has(i);
        const isSelected = selected.has(i);

        let bg = 'var(--bg-elevated)';
        let color = 'var(--text)';
        let border = '1px solid var(--border)';

        if (isMine)          { bg = 'var(--green)'; color = '#eafff1'; border = '1px solid var(--green-bright)'; }
        else if (isTaken)    { bg = 'var(--bg-card-taken)'; color = 'var(--text-faint)'; }
        else if (isSelected) { bg = 'var(--gold)'; color = '#1a1306'; border = '1px solid var(--gold-bright)'; }

        return (
          <button
            key={i}
            onClick={() => onToggle(i)}
            disabled={isTaken || isMine}
            style={{
              background: bg, color, border, borderRadius: 6,
              fontSize: 12, fontWeight: 600, padding: '8px 0',
              cursor: (isTaken || isMine) ? 'default' : 'pointer',
            }}
          >
            {i + 1}
          </button>
        );
      })}
    </div>
  );
}
