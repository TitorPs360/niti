import { useState, useEffect, useCallback } from 'react';
import { GameState, GameScript, GamePhase } from '../types/game';
import { GameAPI } from '../services/api';

export const useGameState = () => {
  const [gameState, setGameState] = useState<GameState>({
    current_state: 'setup',
    script_generated: false,
    assets_generated: false,
    current_game: null,
  });
  const [gameScript, setGameScript] = useState<GameScript | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const pollGameState = useCallback(async () => {
    try {
      const state = await GameAPI.getGameState();
      setGameState(state);
      
      // If game script is ready and we haven't loaded it yet
      if (state.current_game && state.script_generated && !gameScript) {
        const script = await GameAPI.getGameScript(state.current_game);
        setGameScript(script);
      }
    } catch (err) {
      console.error('Failed to poll game state:', err);
    }
  }, [gameScript]);

  useEffect(() => {
    // Initial state fetch
    pollGameState();
    
    // Poll every 2 seconds during setup and generation phases
    const shouldPoll = ['setup', 'setting_up', 'ready', 'generating'].includes(gameState.current_state);
    
    if (shouldPoll) {
      const interval = setInterval(pollGameState, 2000);
      return () => clearInterval(interval);
    }
  }, [gameState.current_state, pollGameState]);

  const setupGame = useCallback(async (ollamaModel?: string) => {
    setLoading(true);
    setError(null);
    try {
      await GameAPI.setupGame(ollamaModel);
      // Polling will handle state updates
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Setup failed');
    } finally {
      setLoading(false);
    }
  }, []);

  const startGame = useCallback(async (extraPrompt?: string) => {
    setLoading(true);
    setError(null);
    try {
      await GameAPI.startGame(extraPrompt);
      // Polling will handle state updates
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to start game');
    } finally {
      setLoading(false);
    }
  }, []);

  const restartGame = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      await GameAPI.restartGame();
      setGameScript(null);
      // Polling will handle state updates
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to restart game');
    } finally {
      setLoading(false);
    }
  }, []);

  const refreshState = useCallback(() => {
    pollGameState();
  }, [pollGameState]);

  return {
    gameState,
    gameScript,
    loading,
    error,
    setupGame,
    startGame,
    restartGame,
    refreshState,
    phase: gameState.current_state as GamePhase,
  };
};