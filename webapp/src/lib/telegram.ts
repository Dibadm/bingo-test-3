declare global {
  interface Window {
    Telegram?: {
      WebApp: TelegramWebApp;
    };
  }
}

interface TelegramWebApp {
  initData: string;
  initDataUnsafe: {
    user?: { id: number; first_name: string; last_name?: string; username?: string; language_code?: string };
    query_id?: string;
    start_param?: string;
  };
  themeParams: Record<string, string>;
  colorScheme: 'light' | 'dark';
  isExpanded: boolean;
  viewportHeight: number;
  viewportStableHeight: number;
  MainButton: {
    text: string; color: string; textColor: string; isVisible: boolean; isActive: boolean;
    show(): void; hide(): void; setText(text: string): void;
    onClick(fn: () => void): void; offClick(fn: () => void): void;
    enable(): void; disable(): void; showProgress(): void; hideProgress(): void;
  };
  BackButton: {
    isVisible: boolean;
    show(): void; hide(): void;
    onClick(fn: () => void): void; offClick(fn: () => void): void;
  };
  HapticFeedback: {
    impactOccurred(style: 'light' | 'medium' | 'heavy' | 'rigid' | 'soft'): void;
    notificationOccurred(type: 'error' | 'success' | 'warning'): void;
    selectionChanged(): void;
  };
  expand(): void;
  close(): void;
  ready(): void;
  showAlert(message: string, callback?: () => void): void;
  showConfirm(message: string, callback: (confirmed: boolean) => void): void;
}

const tg = window.Telegram?.WebApp;
export const isInsideTelegram = !!tg;

if (!isInsideTelegram) {
  console.warn('[telegram.ts] Not running inside Telegram — using mock bridge. API calls requiring real initData will be rejected (expected in dev).');
}

export function ready() { if (isInsideTelegram) tg!.ready(); }
export function expand() { if (isInsideTelegram) tg!.expand(); }
export function getInitData(): string { return isInsideTelegram ? tg!.initData : ''; }
export function getInitDataUnsafe() {
  return isInsideTelegram
    ? tg!.initDataUnsafe
    : { user: { id: 0, username: 'dev', first_name: 'Dev' } };
}
export function close() { if (isInsideTelegram) tg!.close(); }

export function showAlert(message: string) {
  if (isInsideTelegram) {
    tg!.showAlert(message);
  } else {
    window.alert(message);
  }
}

export function showConfirm(message: string): Promise<boolean> {
  return new Promise((resolve) => {
    if (isInsideTelegram) {
      tg!.showConfirm(message, (confirmed) => resolve(confirmed));
    } else {
      resolve(window.confirm(message));
    }
  });
}

export const haptic = {
  light()   { isInsideTelegram && tg!.HapticFeedback?.impactOccurred('light'); },
  medium()  { isInsideTelegram && tg!.HapticFeedback?.impactOccurred('medium'); },
  heavy()   { isInsideTelegram && tg!.HapticFeedback?.impactOccurred('heavy'); },
  success() { isInsideTelegram && tg!.HapticFeedback?.notificationOccurred('success'); },
  error()   { isInsideTelegram && tg!.HapticFeedback?.notificationOccurred('error'); },
};

export function setBackButton(visible: boolean, onClick?: () => void) {
  if (!isInsideTelegram) return;
  if (visible && onClick != null) {
    tg!.BackButton.show();
    tg!.BackButton.onClick(onClick);
  } else {
    tg!.BackButton.hide();
  }
}

export const mainButton = {
  show(text: string, onClick: () => void) {
    if (!isInsideTelegram) return;
    tg!.MainButton.setText(text);
    tg!.MainButton.onClick(onClick);
    tg!.MainButton.show();
  },
  hide()               { if (isInsideTelegram) tg!.MainButton.hide(); },
  setText(text: string){ if (isInsideTelegram) tg!.MainButton.setText(text); },
  offClick(fn: () => void) { if (isInsideTelegram) tg!.MainButton.offClick(fn); },
  enable()             { isInsideTelegram && tg!.MainButton.enable(); },
  disable()            { isInsideTelegram && tg!.MainButton.disable(); },
};
