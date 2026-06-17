import { Routes, Route, Navigate } from 'react-router-dom';
import CardSelection from './pages/CardSelection';
import GameBoard from './pages/GameBoard';

export default function App() {
  return (
    <Routes>
      <Route path="/card-selection" element={<CardSelection />} />
      <Route path="/game" element={<GameBoard />} />
      <Route path="*" element={<Navigate to="/card-selection" replace />} />
    </Routes>
  );
}
