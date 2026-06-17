// src/screens/HomeScreen.jsx
import { useEffect, useState } from 'react';
import { useStore } from '../lib/store';
import { api } from '../lib/api';
import { TopBar, fmt } from '../components/Chrome';
import { haptic } from '../lib/telegram';

export default function HomeScreen({ onEnterRoom }) {
  const { runAction } = useStore();
  const [rooms, setRooms] = useState(null);

  async function load() {
    const res = await runAction(() => api.getRooms());
    setRooms(res.rooms);
  }

  useEffect(() => {
    load();
    const interval = setInterval(load, 4000); // light poll so pool/player counts feel live in the lobby
    return () => clearInterval(interval);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div className="screen">
      <TopBar title="ሀበሻ ቤት" />

      <div style={{ fontSize: 13, color: 'var(--text-dim)', marginTop: -6 }}>
        Pick a room to join the next round
      </div>

      {!rooms && (
        <div className="card" style={{ textAlign: 'center', color: 'var(--text-dim)' }}>
          Loading rooms…
        </div>
      )}

      {rooms && rooms.map(room => (
        <RoomCard
          key={room.room_fee}
          room={room}
          onClick={() => {
            haptic.light();
            onEnterRoom(room.room_fee);
          }}
        />
      ))}
    </div>
  );
}

function RoomCard({ room, onClick }) {
  const busy = room.state === 'running';
  return (
    <button
      className="card btn-block"
      onClick={onClick}
      disabled={busy}
      style={{
        textAlign: 'left', display: 'block', cursor: busy ? 'not-allowed' : 'pointer',
        opacity: busy ? 0.6 : 1, border: '1px solid var(--border)',
      }}
    >
      <div className="row">
        <div style={{ fontSize: 17, fontWeight: 700 }}>
          🎱 Bingo {fmt(room.room_fee)} ETB
        </div>
        {busy ? (
          <span className="pill">🔴 In progress</span>
        ) : (
          <span className="pill">🟢 Open</span>
        )}
      </div>

      <div className="divider" />

      <div className="row">
        <span style={{ fontSize: 13, color: 'var(--text-dim)' }}>Prize pool</span>
        <span style={{ fontWeight: 700, color: 'var(--gold-bright)' }}>{fmt(room.pool)} ETB</span>
      </div>
      <div className="row">
        <span style={{ fontSize: 13, color: 'var(--text-dim)' }}>Cards sold</span>
        <span>{room.cards_sold}/{room.card_pool_size}</span>
      </div>
      <div className="row">
        <span style={{ fontSize: 13, color: 'var(--text-dim)' }}>Players</span>
        <span>👥 {room.player_count}</span>
      </div>
    </button>
  );
}
