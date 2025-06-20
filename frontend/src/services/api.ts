import { GameState, GameScript, ChatResponse, ChatMessage, Character } from '../types/game';

const API_BASE = 'http://localhost:8001/api';

export class GameAPI {
  static async setupGame(ollamaModel = 'gemma3:27b') {
    const response = await fetch(`${API_BASE}/game/setup`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ ollama_model: ollamaModel }),
    });
    
    if (!response.ok) {
      throw new Error(`Setup failed: ${response.statusText}`);
    }
    
    return response.json();
  }

  static async startGame(extraPrompt?: string) {
    const response = await fetch(`${API_BASE}/game/start`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ extra_prompt: extraPrompt }),
    });
    
    if (!response.ok) {
      throw new Error(`Start game failed: ${response.statusText}`);
    }
    
    return response.json();
  }

  static async restartGame() {
    const response = await fetch(`${API_BASE}/game/restart`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
    });
    
    if (!response.ok) {
      throw new Error(`Restart failed: ${response.statusText}`);
    }
    
    return response.json();
  }

  static async getGameState(): Promise<GameState> {
    const response = await fetch(`${API_BASE}/game/state`);
    
    if (!response.ok) {
      throw new Error(`Get game state failed: ${response.statusText}`);
    }
    
    return response.json();
  }

  static async getGameScript(gameId: string): Promise<GameScript> {
    const response = await fetch(`${API_BASE}/game/script/${gameId}`);
    
    if (!response.ok) {
      throw new Error(`Get game script failed: ${response.statusText}`);
    }
    
    return response.json();
  }

  static async getGameImage(imageId: string): Promise<string> {
    const response = await fetch(`${API_BASE}/game/image/${imageId}`, {
      method: 'GET',
      headers: {
        'Accept': 'image/*',
      },
    });
    
    if (!response.ok) {
      const errorText = await response.text();
      throw new Error(`Get image failed: ${response.status} ${response.statusText} - ${errorText}`);
    }
    
    const blob = await response.blob();
    const url = URL.createObjectURL(blob);
    
    return url;
  }

  static async chatWithCharacter(gameId: string, characterName: string, message: string): Promise<ChatResponse> {
    const response = await fetch(`${API_BASE}/game/chat`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        game_id: gameId,
        character_name: characterName,
        message: message,
      }),
    });
    
    if (!response.ok) {
      throw new Error(`Chat failed: ${response.statusText}`);
    }
    
    return response.json();
  }

  static async getChatHistory(gameId: string, characterName: string): Promise<ChatMessage[]> {
    const response = await fetch(`${API_BASE}/game/chat/${gameId}/${characterName}`);
    
    if (!response.ok) {
      throw new Error(`Get chat history failed: ${response.statusText}`);
    }
    
    const data = await response.json();
    return data.messages;
  }

  static async getGameCharacters(gameId: string): Promise<Character[]> {
    const response = await fetch(`${API_BASE}/game/characters/${gameId}`);
    
    if (!response.ok) {
      throw new Error(`Get characters failed: ${response.statusText}`);
    }
    
    const data = await response.json();
    return data.characters;
  }

  static async clearChatHistory(gameId: string) {
    const response = await fetch(`${API_BASE}/game/chat/${gameId}`, {
      method: 'DELETE',
    });
    
    if (!response.ok) {
      throw new Error(`Clear chat history failed: ${response.statusText}`);
    }
    
    return response.json();
  }
}