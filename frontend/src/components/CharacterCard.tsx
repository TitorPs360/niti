import React, { useState, useEffect } from 'react';
import { Character } from '../types/game';
import { GameAPI } from '../services/api';

interface CharacterCardProps {
  character: Character;
  onClick: () => void;
  isSelected?: boolean;
}

export const CharacterCard: React.FC<CharacterCardProps> = ({
  character,
  onClick,
  isSelected = false,
}) => {
  const [imageUrl, setImageUrl] = useState<string | null>(null);
  const [imageLoading, setImageLoading] = useState(false);

  useEffect(() => {
    if (character.image_id && !imageUrl) {
      setImageLoading(true);
      GameAPI.getGameImage(character.image_id)
        .then(setImageUrl)
        .catch((err) => {
          console.error('Failed to load character image:', err);
        })
        .finally(() => setImageLoading(false));
    }
  }, [character.image_id, imageUrl]);

  return (
    <div
      onClick={onClick}
      className={`
        cursor-pointer bg-white rounded-lg shadow-md hover:shadow-lg transition-all duration-200 p-4 border-2
        ${isSelected ? 'border-blue-500 ring-2 ring-blue-200' : 'border-gray-200 hover:border-gray-300'}
      `}
    >
      <div className="flex items-start space-x-4">
        <div className="flex-shrink-0">
          {imageLoading ? (
            <div className="w-16 h-16 bg-gray-200 rounded-full flex items-center justify-center">
              <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-blue-600"></div>
            </div>
          ) : imageUrl ? (
            <img
              src={imageUrl}
              alt={character.name}
              className="w-16 h-16 rounded-full object-cover border-2 border-gray-200"
            />
          ) : (
            <div className="w-16 h-16 bg-gray-300 rounded-full flex items-center justify-center">
              <span className="text-gray-600 text-lg font-medium">
                {character.name.charAt(0)}
              </span>
            </div>
          )}
        </div>
        
        <div className="flex-1">
          <h3 className="text-lg font-semibold text-gray-800 mb-1">
            {character.name}
          </h3>
          <p className="text-sm text-gray-600 mb-1">
            อายุ {character.age} ปี
          </p>
          <p className="text-sm text-gray-700 mb-2">
            {character.role}
          </p>
          <p className="text-xs text-gray-500">
            {character.relationship}
          </p>
        </div>
      </div>
      
      <div className="mt-3 pt-3 border-t border-gray-100">
        <div className="flex items-center justify-between">
          <span className="text-xs text-gray-500">คลิกเพื่อสอบสวน</span>
          <svg
            className="w-4 h-4 text-gray-400"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M9 5l7 7-7 7"
            />
          </svg>
        </div>
      </div>
    </div>
  );
};