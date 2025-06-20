import React, { useState, useEffect } from 'react';
import { Evidence } from '../types/game';
import { GameAPI } from '../services/api';

interface EvidenceCardProps {
  evidence: Evidence;
  onClick?: () => void;
}

export const EvidenceCard: React.FC<EvidenceCardProps> = ({
  evidence,
  onClick,
}) => {
  const [imageUrl, setImageUrl] = useState<string | null>(null);
  const [imageLoading, setImageLoading] = useState(false);
  const [showFullImage, setShowFullImage] = useState(false);

  useEffect(() => {
    if (evidence.image_id && !imageUrl) {
      setImageLoading(true);
      GameAPI.getGameImage(evidence.image_id)
        .then(setImageUrl)
        .catch((err) => {
          console.error('Failed to load evidence image:', err);
        })
        .finally(() => setImageLoading(false));
    }
  }, [evidence.image_id, imageUrl]);

  const handleImageClick = (e: React.MouseEvent) => {
    e.stopPropagation();
    setShowFullImage(true);
  };

  return (
    <>
      <div
        onClick={onClick}
        className="bg-white rounded-lg shadow-md hover:shadow-lg transition-all duration-200 p-4 border border-gray-200 hover:border-gray-300 cursor-pointer"
      >
        <div className="flex items-start space-x-4">
          <div className="flex-shrink-0">
            {imageLoading ? (
              <div className="w-20 h-20 bg-gray-200 rounded-lg flex items-center justify-center">
                <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-blue-600"></div>
              </div>
            ) : imageUrl ? (
              <img
                src={imageUrl}
                alt={evidence.type}
                onClick={handleImageClick}
                className="w-20 h-20 rounded-lg object-cover border border-gray-200 hover:opacity-80 transition-opacity cursor-zoom-in"
              />
            ) : (
              <div className="w-20 h-20 bg-gray-300 rounded-lg flex items-center justify-center">
                <svg
                  className="w-8 h-8 text-gray-500"
                  fill="none"
                  stroke="currentColor"
                  viewBox="0 0 24 24"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"
                  />
                </svg>
              </div>
            )}
          </div>
          
          <div className="flex-1">
            <div className="flex items-center mb-2">
              <span className="inline-block bg-blue-100 text-blue-800 text-xs px-2 py-1 rounded-full font-medium">
                {evidence.type}
              </span>
            </div>
            
            <p className="text-sm text-gray-800 mb-2 leading-relaxed">
              {evidence.description}
            </p>
            
            <p className="text-xs text-gray-500 flex items-center">
              <svg
                className="w-3 h-3 mr-1"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M17.657 16.657L13.414 20.9a1.998 1.998 0 01-2.827 0l-4.244-4.243a8 8 0 1111.314 0z"
                />
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M15 11a3 3 0 11-6 0 3 3 0 016 0z"
                />
              </svg>
              {evidence.location}
            </p>
          </div>
        </div>
      </div>

      {/* Full Image Modal */}
      {showFullImage && imageUrl && (
        <div
          className="fixed inset-0 bg-black bg-opacity-75 flex items-center justify-center z-50 p-4"
          onClick={() => setShowFullImage(false)}
        >
          <div className="relative max-w-4xl max-h-full">
            <img
              src={imageUrl}
              alt={evidence.type}
              className="max-w-full max-h-full object-contain rounded-lg"
            />
            <button
              onClick={() => setShowFullImage(false)}
              className="absolute top-4 right-4 bg-white rounded-full p-2 hover:bg-gray-100 transition-colors"
            >
              <svg
                className="w-6 h-6"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M6 18L18 6M6 6l12 12"
                />
              </svg>
            </button>
          </div>
        </div>
      )}
    </>
  );
};