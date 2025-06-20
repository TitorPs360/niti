import { useState, useEffect, useCallback } from 'react';
import { GameAPI } from '../services/api';

export const useImageLoader = (imageId: string | undefined) => {
  const [imageUrl, setImageUrl] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(false);

  const loadImage = useCallback(async (id: string) => {
    setLoading(true);
    setError(false);
    setImageUrl(null);

    try {
      console.log('Loading image:', id);
      const url = await GameAPI.getGameImage(id);
      setImageUrl(url);
      console.log('Image loaded successfully:', id);
    } catch (err) {
      console.error('Failed to load image:', id, err);
      setError(true);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (!imageId) {
      setImageUrl(null);
      setError(false);
      setLoading(false);
      return;
    }

    loadImage(imageId);
  }, [imageId, loadImage]);

  const retry = useCallback(() => {
    if (imageId) {
      loadImage(imageId);
    }
  }, [imageId, loadImage]);

  return { imageUrl, loading, error, retry };
};