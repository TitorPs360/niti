import { useState, useEffect } from 'react';
import { GameAPI } from '../services/api';

export const useImageLoader = (imageId: string | undefined, maxRetries = 3) => {
  const [imageUrl, setImageUrl] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(false);
  const [retryCount, setRetryCount] = useState(0);

  useEffect(() => {
    if (!imageId) return;

    const loadImage = async () => {
      if (retryCount >= maxRetries) {
        setError(true);
        setLoading(false);
        return;
      }

      setLoading(true);
      setError(false);

      try {
        console.log(`Loading image (attempt ${retryCount + 1}/${maxRetries}):`, imageId);
        
        // Add a small delay for retries
        if (retryCount > 0) {
          await new Promise(resolve => setTimeout(resolve, 1000 * retryCount));
        }

        const url = await GameAPI.getGameImage(imageId);
        setImageUrl(url);
        setLoading(false);
        console.log('Image loaded successfully:', imageId);
      } catch (err) {
        console.error(`Failed to load image (attempt ${retryCount + 1}):`, imageId, err);
        
        if (retryCount < maxRetries - 1) {
          setRetryCount(prev => prev + 1);
        } else {
          setError(true);
          setLoading(false);
        }
      }
    };

    // Reset state when imageId changes
    if (imageId !== imageUrl) {
      setImageUrl(null);
      setError(false);
      setRetryCount(0);
      loadImage();
    }
  }, [imageId, retryCount, maxRetries, imageUrl]);

  const retry = () => {
    if (imageId && error) {
      setRetryCount(0);
      setError(false);
    }
  };

  return { imageUrl, loading, error, retry };
};