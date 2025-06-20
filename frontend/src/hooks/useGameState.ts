import { useState, useEffect, useCallback, useRef } from 'react';
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

  // Use refs to avoid stale closure issues
  const gameStateRef = useRef(gameState);
  const gameScriptRef = useRef(gameScript);
  
  useEffect(() => {
    gameStateRef.current = gameState;
  }, [gameState]);
  
  useEffect(() => {
    gameScriptRef.current = gameScript;
  }, [gameScript]);

  const pollGameState = useCallback(async () => {
    try {
      const state = await GameAPI.getGameState();
      const prevState = gameStateRef.current.current_state;
      setGameState(state);
      
      // Load script when it's ready or when game transitions to playing state
      if (state.current_game && state.script_generated) {
        // Reload script if we don't have one, or if state just changed to "playing"
        const shouldReloadScript = !gameScriptRef.current || 
          (prevState !== 'playing' && state.current_state === 'playing');
        
        if (shouldReloadScript) {
          console.log('Loading game script:', state.current_game, 'state:', state.current_state, 'prevState:', prevState);
          const script = await GameAPI.getGameScript(state.current_game);
          console.log('Loaded script with characters:', script.people?.length, 'evidence:', script.evidence?.length);
          
          // Log image_ids for debugging
          script.people?.forEach((char, i) => {
            console.log(`Character ${i} (${char.name}):`, char.image_id ? `image_id: ${char.image_id}` : 'no image_id');
          });
          script.evidence?.forEach((ev, i) => {
            console.log(`Evidence ${i} (${ev.type}):`, ev.image_id ? `image_id: ${ev.image_id}` : 'no image_id');
          });
          
          setGameScript(script);
        }
      }
    } catch (err) {
      console.error('Failed to poll game state:', err);
    }
  }, []);

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

  const forceReloadScript = useCallback(async () => {
    if (gameStateRef.current.current_game && gameStateRef.current.script_generated) {
      console.log('Force reloading script...');
      try {
        const script = await GameAPI.getGameScript(gameStateRef.current.current_game);
        console.log('Force loaded script with characters:', script.people?.length, 'evidence:', script.evidence?.length);
        setGameScript(script);
      } catch (err) {
        console.error('Failed to force reload script:', err);
      }
    }
  }, []);

  return {
    gameState,
    gameScript,
    loading,
    error,
    setupGame,
    startGame,
    restartGame,
    refreshState,
    forceReloadScript,
    phase: gameState.current_state as GamePhase,
  };
};