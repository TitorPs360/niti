import React, { useState } from 'react';
import { GameScript } from '../types/game';

interface DebugPanelProps {
  gameScript: GameScript | null;
  gameId: string | null;
  onForceReload?: () => void;
}

export const DebugPanel: React.FC<DebugPanelProps> = ({ gameScript, gameId, onForceReload }) => {
  const [isOpen, setIsOpen] = useState(false);

  if (!gameScript) return null;

  return (
    <div className="fixed bottom-4 right-4 z-50">
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="bg-purple-600 hover:bg-purple-700 text-white px-3 py-2 rounded-md text-sm font-medium shadow-lg"
      >
        Debug {isOpen ? '✕' : '🔍'}
      </button>

      {isOpen && (
        <div className="absolute bottom-12 right-0 w-96 max-h-96 bg-white border border-gray-300 rounded-lg shadow-xl overflow-auto">
          <div className="p-4">
            <h3 className="font-semibold text-gray-800 mb-3">Debug Information</h3>
            
            <div className="space-y-3 text-sm">
              <div>
                <span className="font-medium">Game ID:</span> {gameId}
              </div>
              
              <div>
                <span className="font-medium">Characters:</span>
                <div className="ml-2 space-y-1">
                  {gameScript.people.map((character, index) => (
                    <div key={index} className="text-xs">
                      <div>{character.name}</div>
                      <div className="text-gray-600 ml-2">
                        image_id: {character.image_id || 'none'}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
              
              <div>
                <span className="font-medium">Evidence:</span>
                <div className="ml-2 space-y-1">
                  {gameScript.evidence.map((evidence, index) => (
                    <div key={index} className="text-xs">
                      <div>{evidence.type}</div>
                      <div className="text-gray-600 ml-2">
                        image_id: {evidence.image_id || 'none'}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
              
              <div>
                <span className="font-medium">API URLs:</span>
                <div className="ml-2 space-y-1 text-xs">
                  <div>Base: http://localhost:8001/api</div>
                  <div>State: GET /game/state</div>
                  <div>Script: GET /game/script/{gameId}</div>
                  <div>Images: GET /game/image/{'<image_id>'}</div>
                </div>
              </div>
              
              {onForceReload && (
                <div>
                  <button
                    onClick={onForceReload}
                    className="w-full bg-blue-600 hover:bg-blue-700 text-white text-xs px-2 py-1 rounded"
                  >
                    Force Reload Script
                  </button>
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
};