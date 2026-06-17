// src/screens/LiveGameScreen.jsx
import { useEffect, useState, useRef, useCallback } from 'react';
import { useStore } from '../lib/store';
import { api } from '../lib/api';
import { fmt } from '../components/Chrome';
import { haptic, mainButton, showAlert } from '../lib/telegram';

const LETTERS = ['B', 'I', 'N', 'G', 'O'];

export default function LiveGameScreen({ gameId, onFinished }) {
  const { user, runAction, refreshUser } = useStore();
  const [state, setState] = useState(null);
  const pollRef = useRef(null);

  const poll = useCallback(async () => {
    try {
      const res = await api.getGameState(gameId);
      setState(res);
      if (res.state === 'finished') {
        clearInterval(pollRef.current);
        await refreshUser();
      }
    } catch (e) {
      // Transient network hiccup mid-game shouldn't kill the screen -
      // just skip this tick and try again on the next interval.
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [gameId]);

  useEffect(() => {
    poll();
    pollRef.current = setInterval(poll, 1800);
    return () => clearInterval(pollRef.current);
  }, [poll]);

  const toggleAuto = async () => {
    const next = !state.auto_win;
    haptic.light();
    await runAction(() => api.toggleAutoWin(gameId, next));
    setState(prev => ({ ...prev, auto_win: next }));
  };

  const claimBingo = async () => {
    haptic.medium();
    try {
      await runAction(() => api.claimBingo(gameId));
      showAlert('Claim received! Confirming…');
    } catch {
      // already toasted
    }
  };

  useEffect(() => {
    if (!state || state.state !== 'running') {
      mainButton.hide();
      return;
    }
    mainButton.show('🎯 BINGO!', claimBingo);
    return () => mainButton.offClick(claimBingo);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [state?.state]);

  if (!state) {
    return <div className="screen"><div className="card" style={{ textAlign: 'center' }}>Loading game…</div></div>;
  }

  if (state.state === 'waiting') {
    return (
      <div className="screen">
        <div className="card" style={{ textAlign: 'center' }}>
          <div style={{ fontSize: 18, fontWeight: 700, marginBottom: 6 }}>⏳ Waiting for players…</div>
          <div style={{ color: 'var(--text-dim)', fontSize: 13 }}>Prize pool: {fmt(state.pool)} ETB</div>
        </div>
      </div>
    );
  }

  if (state.state === 'finished') {
    return <ResultScreen state={state} onDone={onFinished} />;
  }

  return (
    <div className="screen">
      <div className="row">
        <div style={{ fontWeight: 700 }}>Bingo {fmt(state.room_fee)} ETB</div>
        <div className="pill pill-gold">💰 {fmt(user?.balance)} ETB</div>
      </div>

      <div className="card" style={{ textAlign: 'center' }}>
        <div style={{ fontSize: 12, color: 'var(--text-dim)' }}>Call {state.call_count}/{state.max_calls}</div>
        {state.last_call && (
          <div style={{ fontSize: 34, fontWeight: 800, color: 'var(--gold-bright)', margin: '4px 0' }}>
            {state.last_call.letter}-{state.last_call.number}
          </div>
        )}
        {state.last_call && (
          <div style={{ fontSize: 13, color: 'var(--text-dim)' }}>{state.last_call.amharic}</div>
        )}
        <div style={{ fontSize: 12, color: 'var(--text-dim)', marginTop: 6 }}>
          🏆 Pool: {fmt(state.pool)} ETB · 👥 {state.player_count} players
        </div>
      </div>

      <NumberGrid called={state.called_numbers} />

      <button
        className={`btn ${state.auto_win ? 'btn-success' : 'btn-secondary'} btn-block`}
        onClick={toggleAuto}
      >
        🤖 Auto-win: {state.auto_win ? 'ON' : 'OFF'}
      </button>

      {state.my_cards.map(card => (
        <CardView key={card.card_index} card={card} />
      ))}
    </div>
  );
}

function NumberGrid({ called }) {
  const calledSet = new Set(called);
  const cells = [];
  for (let n = 1; n <= 75; n++) {
    cells.push(
      <div
        key={n}
        style={{
          fontSize: 10, textAlign: 'center', padding: '4px 0', borderRadius: 4,
          background: calledSet.has(n) ? 'var(--gold)' : 'var(--bg-elevated)',
          color: calledSet.has(n) ? '#1a1306' : 'var(--text-faint)',
          fontWeight: calledSet.has(n) ? 700 : 400,
        }}
      >
        {n}
      </div>
    );
  }
  return (
    <div className="card">
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(15, 1fr)', gap: 3 }}>
        {cells}
      </div>
    </div>
  );
}

function CardView({ card }) {
  const calledSet = new Set(card.called);
  return (
    <div className="card">
      <div style={{ fontSize: 12, color: 'var(--text-dim)', marginBottom: 8 }}>Cartela #{card.card_number}</div>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(5, 1fr)', gap: 4 }}>
        {LETTERS.map(l => (
          <div key={l} style={{ textAlign: 'center', fontSize: 11, fontWeight: 700, color: 'var(--gold-bright)' }}>{l}</div>
        ))}
        {[0, 1, 2, 3, 4].map(row => (
          card.grid.map((col, colIdx) => {
            const value = col[row];
            const isFree = value === 0;
            const isCalled = !isFree && calledSet.has(value);
            return (
              <div
                key={`${colIdx}-${row}`}
                style={{
                  textAlign: 'center', padding: '8px 0', borderRadius: 6, fontSize: 13, fontWeight: 600,
                  background: isFree ? 'var(--border)' : isCalled ? 'var(--green)' : 'var(--bg-elevated)',
                  color: isFree ? 'var(--text-dim)' : isCalled ? '#eafff1' : 'var(--text)',
                }}
              >
                {isFree ? '★' : value}
              </div>
            );
          })
        ))}
      </div>
    </div>
  );
}

function ResultScreen({ state, onDone }) {
  const won = state.i_won;
  return (
    <div className="screen">
      <div
        className="card"
        style={{
          textAlign: 'center', padding: 28,
          background: won ? 'linear-gradient(160deg, #1d4a2c, #0d2a18)' : 'var(--bg-card)',
          border: won ? '1px solid var(--green-bright)' : '1px solid var(--border)',
        }}
      >
        <div style={{ fontSize: 40 }}>{won ? '🏆' : '😮'}</div>
        <div style={{ fontSize: 20, fontWeight: 800, marginTop: 8 }}>
          {won ? 'You won!' : state.winners.length > 0 ? 'Round over' : 'No winner — refunded'}
        </div>
        {won && (
          <div style={{ fontSize: 28, fontWeight: 800, color: 'var(--gold-bright)', marginTop: 6 }}>
            +{fmt(state.per_winner_amount)} ETB
          </div>
        )}
        {!won && state.winners.length > 0 && (
          <div style={{ fontSize: 13, color: 'var(--text-dim)', marginTop: 6 }}>
            {state.winners.length} winner{state.winners.length > 1 ? 's' : ''} split {fmt(state.per_winner_amount)} ETB each
          </div>
        )}
      </div>
      <button className="btn btn-primary btn-block" onClick={onDone}>Back to Lobby</button>
    </div>
  );
}
