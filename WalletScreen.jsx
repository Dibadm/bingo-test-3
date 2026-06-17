// src/screens/WalletScreen.jsx
import { useState } from 'react';
import { useStore } from '../lib/store';
import { api } from '../lib/api';
import { TopBar, fmt } from '../components/Chrome';
import { haptic } from '../lib/telegram';

const TABS = ['deposit', 'withdraw', 'transfer'];

export default function WalletScreen() {
  const [tab, setTab] = useState('deposit');
  return (
    <div className="screen">
      <TopBar title="Wallet" />

      <div style={{ display: 'flex', gap: 6 }}>
        {TABS.map(t => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className="btn"
            style={{
              flex: 1, padding: '10px 0', fontSize: 13,
              background: tab === t ? 'var(--gold)' : 'var(--bg-elevated)',
              color: tab === t ? '#1a1306' : 'var(--text-dim)',
            }}
          >
            {t === 'deposit' && '💳 Deposit'}
            {t === 'withdraw' && '💸 Withdraw'}
            {t === 'transfer' && '🔁 Transfer'}
          </button>
        ))}
      </div>

      {tab === 'deposit' && <DepositPanel />}
      {tab === 'withdraw' && <WithdrawPanel />}
      {tab === 'transfer' && <TransferPanel />}
    </div>
  );
}

function DepositPanel() {
  const { runAction, refreshUser, showToast } = useStore();
  const [account, setAccount] = useState(null);
  const [amount, setAmount] = useState('');
  const [smsText, setSmsText] = useState('');
  const [submitting, setSubmitting] = useState(false);

  const loadAccount = async () => {
    const res = await runAction(() => api.getDepositAccount());
    setAccount(res);
  };

  const submit = async () => {
    if (!smsText.trim()) return;
    setSubmitting(true);
    try {
      const res = await runAction(() =>
        api.submitDepositSms(smsText.trim(), amount ? Number(amount) : undefined)
      );
      haptic.success();
      showToast(`Deposit confirmed: +${fmt(res.amount_credited)} ETB`, 'success');
      setSmsText('');
      await refreshUser();
    } catch {
      // already toasted
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="card" style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
      {!account && (
        <button className="btn btn-secondary btn-block" onClick={loadAccount}>
          Show deposit account
        </button>
      )}

      {account && (
        <>
          <div style={{ fontSize: 13, color: 'var(--text-dim)' }}>Send Telebirr payment to:</div>
          <div className="row">
            <span style={{ fontWeight: 700, fontSize: 16 }}>📱 {account.phone}</span>
          </div>
          <div style={{ fontSize: 13, color: 'var(--text-dim)' }}>Account name: {account.recipient_name}</div>

          <div className="divider" />

          <label className="label">Amount sent (optional, helps verify faster)</label>
          <input className="input" type="number" placeholder="e.g. 100" value={amount} onChange={e => setAmount(e.target.value)} />

          <label className="label">Paste the full Telebirr confirmation SMS</label>
          <textarea
            className="input"
            rows={5}
            placeholder="Dear ... You have transferred ETB ..."
            value={smsText}
            onChange={e => setSmsText(e.target.value)}
          />

          <button className="btn btn-primary btn-block" onClick={submit} disabled={submitting || !smsText.trim()}>
            {submitting ? 'Verifying…' : 'Confirm Deposit'}
          </button>
        </>
      )}
    </div>
  );
}

function WithdrawPanel() {
  const { user, runAction, refreshUser, showToast } = useStore();
  const [amount, setAmount] = useState('');
  const [submitting, setSubmitting] = useState(false);

  const submit = async () => {
    const value = Number(amount);
    if (!value || value <= 0) return;
    setSubmitting(true);
    try {
      await runAction(() => api.withdraw(value));
      haptic.success();
      showToast('Withdrawal requested — processed within 24h.', 'success');
      setAmount('');
      await refreshUser();
    } catch {
      // already toasted
    } finally {
      setSubmitting(false);
    }
  };

  if (!user?.phone) {
    return (
      <div className="card">
        <div style={{ color: 'var(--text-dim)', fontSize: 14 }}>
          ⚠️ No phone number on file. Open the bot chat and send /start to register your number before withdrawing.
        </div>
      </div>
    );
  }

  return (
    <div className="card" style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
      <div style={{ fontSize: 13, color: 'var(--text-dim)' }}>Withdrawals are sent to your registered phone: <b>{user.phone}</b></div>
      <label className="label">Amount (ETB)</label>
      <input className="input" type="number" placeholder="Amount" value={amount} onChange={e => setAmount(e.target.value)} />
      <button className="btn btn-primary btn-block" onClick={submit} disabled={submitting || !amount}>
        {submitting ? 'Submitting…' : 'Request Withdrawal'}
      </button>
    </div>
  );
}

function TransferPanel() {
  const { runAction, refreshUser, showToast } = useStore();
  const [username, setUsername] = useState('');
  const [amount, setAmount] = useState('');
  const [submitting, setSubmitting] = useState(false);

  const submit = async () => {
    const value = Number(amount);
    if (!username.trim() || !value || value <= 0) return;
    setSubmitting(true);
    try {
      await runAction(() => api.transfer(username.trim().replace(/^@/, ''), value));
      haptic.success();
      showToast(`Sent ${fmt(value)} ETB to @${username.trim().replace(/^@/, '')}`, 'success');
      setUsername('');
      setAmount('');
      await refreshUser();
    } catch {
      // already toasted
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="card" style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
      <label className="label">Recipient username</label>
      <input className="input" placeholder="@username" value={username} onChange={e => setUsername(e.target.value)} />
      <label className="label">Amount (ETB)</label>
      <input className="input" type="number" placeholder="Amount" value={amount} onChange={e => setAmount(e.target.value)} />
      <button className="btn btn-primary btn-block" onClick={submit} disabled={submitting || !username || !amount}>
        {submitting ? 'Sending…' : 'Send Transfer'}
      </button>
    </div>
  );
}
