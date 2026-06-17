// src/components/Chrome.jsx
import { useStore } from '../lib/store';

export function TopBar({ title }) {
  const { user } = useStore();
  return (
    <div className="row" style={{ paddingBottom: 4 }}>
      <div style={{ fontFamily: 'var(--font-display)', fontSize: 20, fontWeight: 700, color: 'var(--gold-bright)' }}>
        {title}
      </div>
      {user && (
        <div className="pill pill-gold">
          💰 {fmt(user.balance)} ETB
        </div>
      )}
    </div>
  );
}

export function fmt(n) {
  const num = Number(n);
  return num % 1 === 0 ? String(num) : num.toFixed(2);
}

const TABS = [
  { key: 'home', icon: '🏠', label: 'Home' },
  { key: 'wallet', icon: '💳', label: 'Wallet' },
  { key: 'profile', icon: '👤', label: 'Profile' },
];

export function BottomNav({ active, onChange }) {
  return (
    <div style={{
      position: 'fixed', bottom: 0, left: 0, right: 0,
      display: 'flex', background: 'var(--bg-elevated)',
      borderTop: '1px solid var(--border)', paddingBottom: 'env(safe-area-inset-bottom)',
      zIndex: 50,
    }}>
      {TABS.map(t => (
        <button
          key={t.key}
          onClick={() => onChange(t.key)}
          className="btn"
          style={{
            flex: 1, background: 'transparent', borderRadius: 0,
            flexDirection: 'column', gap: 2, padding: '10px 0 8px',
            color: active === t.key ? 'var(--gold-bright)' : 'var(--text-faint)',
          }}
        >
          <span style={{ fontSize: 20 }}>{t.icon}</span>
          <span style={{ fontSize: 11, fontWeight: 500 }}>{t.label}</span>
        </button>
      ))}
    </div>
  );
}

export function Toast() {
  const { toast } = useStore();
  if (!toast) return null;
  return (
    <div className="toast" key={toast.key}>
      {toast.message}
    </div>
  );
}

export function FullScreenLoader() {
  return (
    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100vh' }}>
      <div className="spinner" />
    </div>
  );
}
