export interface GameState {
  current_state: string;
  script_generated: boolean;
  assets_generated: boolean;
  current_game: string | null;
}

export interface Character {
  name: string;
  age: string;
  role: string;
  relationship: string;
  characteristics?: string;
  secret: string;
  motive: string;
  alibi: string;
  details: string;
  image_id?: string;
}

export interface Evidence {
  type: string;
  description: string;
  location: string;
  image_generation_prompt?: string;
  image_id?: string;
}

export interface GameScript {
  situation: {
    location: string;
    time: string;
    victim: string;
    age: string;
    cause_of_death: string;
    details: string;
  };
  people: Character[];
  evidence: Evidence[];
  resolution: {
    culprit: string;
    description: string;
  };
}

export interface ChatMessage {
  role: 'user' | 'character';
  content: string;
  timestamp: string;
}

export interface ChatResponse {
  character_name: string;
  response: string;
  timestamp: string;
}

export type GamePhase = 'setup' | 'setting_up' | 'ready' | 'generating' | 'playing' | 'setup_error' | 'generation_error';