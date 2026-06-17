// src/screens/CardSelectScreen.jsx
import { useEffect, useState, useCallback } from 'react';
import { useStore } from '../lib/store';
import { api } from '../lib/api';
import { fmt } from '../components/Chrome';
import { haptic, mainButton, showAlert } from '../lib/telegram';

export default function CardSelectScreen({ roomFee, onBack, onGameStart }) {
  const { user, runAction, refreshUser } = useStore();
  const [data, setData] = useState(null);
  const [selected, setSelected] = useState(new Set());
  const [buying, setBuying] = useState(false);

  const load = useCallback(async () => {
    const res = await runAction(() => api.getRoomCards(roomFee));
    setData(res);
    // If the room moved to "running" while we were picking (someone
    // else's purchase triggered the countdown to finish), bounce
    // straight into the live game screen instead of leaving the player
    // stuck on a selection grid for a round that already started.
    if (res.state === 'running') {
      onGameStart(res.game_id);
    }
    return res;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [roomFee]);

  useEffect(() => {
    load();
    const interval = setInterval(load, 2500); // keep taken/sold counts fresh as others buy
    return () => clearInterval(interval);
  }, [load]);

  const toggle = (idx) => {
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

  const randomPick = (count) => {
    if (!data) return;
    const taken = new Set([...data.taken_cards, ...data.my_cards, ...selected]);
    const available = [];
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
      if (fresh.state === 'running') onGameStart(fresh.game_id);
    } catch {
      // runAction already toasted the error; just refresh so stale
      // "taken" state (e.g. someone grabbed a card we picked) clears.
      await load();
    } finally {
      setBuying(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selected, roomFee]);

  // Telegram's native bottom MainButton drives the actual purchase -
  // feels more "native" than an in-page button and is always visible
  // regardless of scroll position.
  useEffect(() => {
    if (!data) return;
    const cost = selected.size * roomFee;
    if (selected.size === 0) {
      mainButton.hide();
      return;
    }
    mainButton.show(`Buy ${selected.size} card${selected.size > 1 ? 's' : ''} — ${fmt(cost)} ETB`, confirmPurchase);
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
      </div>

      {data.my_cards.length > 0 && (
        <div className="pill pill-gold" style={{ alignSelf: 'flex-start' }}>
          ✅ You already hold {data.my_cards.length} card{data.my_cards.length > 1 ? 's' : ''} this round
        </div>
      )}

      <div style={{ display: 'flex', gap: 8 }}>
        <button className="btn btn-secondary" style={{ flex: 1 }} onClick={() => randomPick(1)}>🎲 Random x1</button>
        <button className="btn btn-secondary" style={{ flex: 1 }} onClick={() => randomPick(2)}>🎲 Random x2</button>
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

function CardGrid({ poolSize, taken, mine, selected, onToggle }) {
  const takenSet = new Set(taken);
  const mineSet = new Set(mine);

  const cells = [];
  for (let i = 0; i < poolSize; i++) {
    const isTaken = takenSet.has(i);
    const isMine = mineSet.has(i);
    const isSelected = selected.has(i);

    let bg = 'var(--bg-elevated)';
    let color = 'var(--text)';
    let border = '1px solid var(--border)';

    if (isMine) {
      bg = 'var(--green)'; color = '#eafff1'; border = '1px solid var(--green-bright)';
    } else if (isTaken) {
      bg = 'var(--bg-card-taken)'; color = 'var(--text-faint)';
    } else if (isSelected) {
      bg = 'var(--gold)'; color = '#1a1306'; border = '1px solid var(--gold-bright)';
    }

    cells.push(
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
  }

  return (
    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(10, 1fr)', gap: 5 }}>
      {cells}
    </div>
  );
}
