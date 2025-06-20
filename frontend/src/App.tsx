import React from 'react';
import { useGameState } from './hooks/useGameState';
import { GameSetup } from './components/GameSetup';
import { GameBoard } from './components/GameBoard';
import './App.css';

function App() {
  const {
    gameState,
    gameScript,
    loading,
    error,
    setupGame,
    startGame,
    restartGame,
    phase,
  } = useGameState();

  // Show game board if we're in playing state and have a script
  if (phase === 'playing' && gameScript && gameState.current_game) {
    return (
      <GameBoard
        gameScript={gameScript}
        gameId={gameState.current_game}
        onRestart={restartGame}
      />
    );
  }

  // Show setup interface for all other states
  return (
    <div className="min-h-screen bg-gray-100 flex items-center justify-center">
      <GameSetup
        phase={phase}
        loading={loading}
        error={error}
        onSetup={setupGame}
        onStart={startGame}
      />
    </div>
  );
}

export default App;
