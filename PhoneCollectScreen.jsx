// src/screens/PhoneCollectScreen.jsx
import { useState } from 'react';
import { useStore } from '../lib/store';
import { api } from '../lib/api';
import { haptic } from '../lib/telegram';

export default function PhoneCollectScreen({ onDone }) {
  const { runAction, refreshUser, showToast } = useStore();
  const [phone, setPhone] = useState('');
  const [submitting, setSubmitting] = useState(false);

  const submit = async () => {
    if (phone.trim().length < 8) {
      showToast('Enter a valid phone number.');
      return;
    }
    setSubmitting(true);
    try {
      await runAction(() => api.setPhone(phone.trim()));
      haptic.success();
      await refreshUser();
      onDone();
    } catch {
      // already toasted
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="screen" style={{ justifyContent: 'center' }}>
      <div style={{ textAlign: 'center', marginBottom: 8 }}>
        <div style={{ fontFamily: 'var(--font-display)', fontSize: 28, fontWeight: 700, color: 'var(--gold-bright)' }}>
          ሀበሻ ቤት
        </div>
        <div style={{ fontSize: 13, color: 'var(--text-dim)', marginTop: 4 }}>Habesha Bet</div>
      </div>

      <div className="card">
        <div style={{ fontSize: 14, marginBottom: 12 }}>
          📱 Enter your Telebirr phone number so we can send your withdrawals here.
        </div>
        <input
          className="input"
          placeholder="09XXXXXXXX"
          value={phone}
          onChange={e => setPhone(e.target.value)}
          inputMode="tel"
        />
        <button className="btn btn-primary btn-block" style={{ marginTop: 14 }} onClick={submit} disabled={submitting}>
          {submitting ? 'Saving…' : 'Continue'}
        </button>
      </div>
    </div>
  );
}
