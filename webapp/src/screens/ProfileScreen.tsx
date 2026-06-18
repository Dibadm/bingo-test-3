import { useEffect, useState } from 'react';
import { useStore } from '../lib/store';
import { api } from '../lib/api';
import { TopBar, fmt } from '../components/Chrome';
import { haptic } from '../lib/telegram';

const TX_ICON: Record<string, string> = {
  deposit: '💳', withdraw: '💸', withdraw_refund: '↩️',
  transfer_in: '📥', transfer_out: '📤',
  bingo_bet: '🎲', bingo_win: '🏆', bingo_refund: '↩️',
  referral_bonus: '👥', signup_bonus: '🎁', daily_bonus: '🎁',
  win: '🏆', card_buy: '🎲', refund: '↩️', transfer_out_tx: '📤', transfer_in_tx: '📥',
};

export default function ProfileScreen() {
  const { user, runAction, refreshUser, showToast } = useStore();
  const [profile, setProfile] = useState<any>(null);
  const [referral, setReferral] = useState<any>(null);
  const [transactions, setTransactions] = useState<any[] | null>(null);

  useEffect(() => {
    runAction(() => api.getProfile()).then(setProfile).catch(() => {});
    runAction(() => api.getReferral()).then(setReferral).catch(() => {});
    runAction(() => api.getTransactions(15)).then(r => setTransactions(r.transactions ?? r)).catch(() => {});
  }, []);

  const claimBonus = async () => {
    haptic.light();
    try {
      const res = await runAction(() => api.claimDailyBonus());
      haptic.success();
      showToast(`+${fmt(res.amount)} ETB daily bonus claimed!`, 'success');
      await refreshUser();
    } catch {
      // already toasted
    }
  };

  const toggleLanguage = async () => {
    const next = user?.language === 'am' ? 'en' : 'am';
    await runAction(() => api.setLanguage(next));
    await refreshUser();
  };

  const copyReferralLink = async () => {
    if (!referral) return;
    try {
      await navigator.clipboard.writeText(referral.link);
      showToast('Referral link copied!', 'success');
    } catch {
      showToast(referral.link, 'success');
    }
  };

  return (
    <div className="screen">
      <TopBar title="Profile" />

      <div className="card">
        <div style={{ fontSize: 16, fontWeight: 700 }}>
          @{user?.username || user?.telegram_id}
        </div>
        <div style={{ fontSize: 13, color: 'var(--text-dim)', marginTop: 2 }}>
          📱 {user?.phone || 'No phone on file'}
        </div>
        {profile && (
          <div style={{ fontSize: 12, color: 'var(--text-faint)', marginTop: 4 }}>
            Joined {profile.joined?.slice(0, 10)}
          </div>
        )}
      </div>

      <button className="btn btn-success btn-block" onClick={claimBonus}>
        🎁 Claim Daily Bonus
      </button>

      {referral && (
        <div className="card">
          <div style={{ fontWeight: 700, marginBottom: 6 }}>👥 Invite Friends</div>
          <div style={{ fontSize: 13, color: 'var(--text-dim)' }}>
            They get {fmt(referral.signup_bonus)} ETB on joining.
            You get {fmt(referral.referral_bonus)} ETB when they deposit.
          </div>
          <div style={{ fontSize: 13, marginTop: 6 }}>
            Referrals so far: <b>{referral.referral_count}</b>
          </div>
          <button className="btn btn-secondary btn-block" style={{ marginTop: 10 }}
            onClick={copyReferralLink}>
            📋 Copy referral link
          </button>
        </div>
      )}

      <button className="btn btn-secondary btn-block" onClick={toggleLanguage}>
        🌐 Language: {user?.language === 'am' ? 'አማርኛ' : 'English'} (tap to switch)
      </button>

      <div className="card">
        <div style={{ fontWeight: 700, marginBottom: 8 }}>Recent Transactions</div>
        {!transactions && (
          <div style={{ color: 'var(--text-dim)', fontSize: 13 }}>Loading…</div>
        )}
        {transactions?.length === 0 && (
          <div style={{ color: 'var(--text-dim)', fontSize: 13 }}>No transactions yet.</div>
        )}
        {transactions?.map((tx, i) => (
          <div
            key={i}
            className="row"
            style={{
              padding: '8px 0',
              borderBottom: i < transactions.length - 1 ? '1px solid var(--border)' : 'none',
            }}
          >
            <span style={{ fontSize: 13 }}>
              {TX_ICON[tx.type] || '•'} {tx.type.replace(/_/g, ' ')}
            </span>
            <span style={{
              fontWeight: 700, fontSize: 13,
              color: tx.amount >= 0 ? 'var(--green-bright)' : 'var(--danger)',
            }}>
              {tx.amount >= 0 ? '+' : ''}{fmt(tx.amount)} ETB
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}
