import { createContext, useContext, useState, useCallback, ReactNode } from 'react';
import { api } from './api';

interface User {
  telegram_id: number;
  username: string;
  first_name: string;
  phone: string;
  balance: number;
  language: 'en' | 'am';
  referral_code: string;
}

interface Toast {
  message: string;
  kind: 'error' | 'success';
  key: number;
}

interface StoreValue {
  user: User | null;
  setUser: (u: User) => void;
  loading: boolean;
  toast: Toast | null;
  fatalError: string | null;
  init: () => Promise<void>;
  refreshUser: () => Promise<{ user: User }>;
  runAction: <T>(fn: () => Promise<T>) => Promise<T>;
  showToast: (message: string, kind?: 'error' | 'success') => void;
}

const StoreContext = createContext<StoreValue | null>(null);

export function StoreProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const [toast, setToast] = useState<Toast | null>(null);
  const [fatalError, setFatalError] = useState<string | null>(null);

  const showToast = useCallback((message: string, kind: 'error' | 'success' = 'error') => {
    setToast({ message, kind, key: Date.now() });
    window.clearTimeout((window as any).__toastTimer);
    (window as any).__toastTimer = window.setTimeout(() => setToast(null), 3200);
  }, []);

  const refreshUser = useCallback(async () => {
    try {
      const res = await api.bootstrap();
      setUser(res.user);
      return res;
    } catch (e: any) {
      setFatalError(e.message || 'Could not connect to the server.');
      throw e;
    }
  }, []);

  const init = useCallback(async () => {
    setLoading(true);
    try {
      await refreshUser();
    } finally {
      setLoading(false);
    }
  }, [refreshUser]);

  const runAction = useCallback(async <T,>(fn: () => Promise<T>): Promise<T> => {
    try {
      return await fn();
    } catch (e: any) {
      showToast(e.message || 'Something went wrong.');
      throw e;
    }
  }, [showToast]);

  return (
    <StoreContext.Provider value={{ user, setUser, loading, toast, fatalError, init, refreshUser, runAction, showToast }}>
      {children}
    </StoreContext.Provider>
  );
}

export function useStore(): StoreValue {
  const ctx = useContext(StoreContext);
  if (!ctx) throw new Error('useStore must be used inside StoreProvider');
  return ctx;
}
