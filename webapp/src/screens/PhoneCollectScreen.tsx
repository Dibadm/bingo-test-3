import { useState } from 'react';
import { useStore } from '../lib/store';
import { api } from '../lib/api';
import { haptic } from '../lib/telegram';

export default function PhoneCollectScreen({ onDone }: { onDone: () => void }) {
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

      <div className="card" style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
        <div style={{ fontSize: 14 }}>
          📱 Enter your Telebirr phone number so we can send your withdrawals here.
        </div>
        <label className="label">Phone number</label>
        <input
          className="input"
          type="tel"
          placeholder="e.g. 0912345678"
          value={phone}
          onChange={e => setPhone(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && submit()}
        />
        <button className="btn btn-primary btn-block" onClick={submit}
          disabled={submitting || phone.trim().length < 8}>
          {submitting ? 'Saving…' : 'Continue →'}
        </button>
      </div>
    </div>
  );
}
