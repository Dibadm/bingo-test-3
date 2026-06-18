import { useEffect, useState } from 'react';
import { StoreProvider, useStore } from './lib/store';
import { ready, expand, setBackButton } from './lib/telegram';
import { FullScreenLoader, BottomNav, Toast } from './components/Chrome';
import type { TabKey } from './components/Chrome';

import PhoneCollectScreen from './screens/PhoneCollectScreen';
import HomeScreen from './screens/HomeScreen';
import CardSelectScreen from './screens/CardSelectScreen';
import LiveGameScreen from './screens/LiveGameScreen';
import WalletScreen from './screens/WalletScreen';
import ProfileScreen from './screens/ProfileScreen';

type View =
  | { name: TabKey }
  | { name: 'cardselect'; roomFee: number }
  | { name: 'livegame'; gameId: number };

function Shell() {
  const { user, loading, init, fatalError } = useStore();
  const [view, setView] = useState<View>({ name: 'home' });

  useEffect(() => {
    ready();
    expand();
    init();
  }, []);

  useEffect(() => {
    const isRoot = view.name === 'home' || view.name === 'wallet' || view.name === 'profile';
    if (isRoot) {
      setBackButton(false);
      return;
    }
    setBackButton(true, goHome);
  }, [view]);

  const goHome   = () => setView({ name: 'home' });
  const enterRoom = (roomFee: number) => setView({ name: 'cardselect', roomFee });
  const enterGame = (gameId: number) => setView({ name: 'livegame', gameId });

  if (fatalError) {
    return (
      <div className="screen" style={{ justifyContent: 'center', textAlign: 'center' }}>
        <div style={{ fontSize: 32 }}>⚠️</div>
        <div style={{ fontWeight: 700, marginTop: 8 }}>Could not connect</div>
        <div style={{ color: 'var(--text-dim)', fontSize: 13, marginTop: 4 }}>{fatalError}</div>
      </div>
    );
  }

  if (loading || !user) return <FullScreenLoader />;

  if (!user.phone) {
    return <PhoneCollectScreen onDone={goHome} />;
  }

  const isRootTab = view.name === 'home' || view.name === 'wallet' || view.name === 'profile';

  return (
    <>
      {view.name === 'home' && <HomeScreen onEnterRoom={enterRoom} />}
      {view.name === 'wallet' && <WalletScreen />}
      {view.name === 'profile' && <ProfileScreen />}
      {view.name === 'cardselect' && 'roomFee' in view && (
        <CardSelectScreen roomFee={view.roomFee} onBack={goHome} onGameStart={enterGame} />
      )}
      {view.name === 'livegame' && 'gameId' in view && (
        <LiveGameScreen gameId={view.gameId} onFinished={goHome} />
      )}

      {isRootTab && (
        <BottomNav
          active={view.name as TabKey}
          onChange={(name) => setView({ name })}
        />
      )}

      <Toast />
    </>
  );
}

export default function App() {
  return (
    <StoreProvider>
      <Shell />
    </StoreProvider>
  );
}
