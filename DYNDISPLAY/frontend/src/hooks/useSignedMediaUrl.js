import { useEffect, useState } from 'react';
import { apiService } from '../services/api';

// Cache mémoire des URL signées, avec TTL en deçà de MEDIA_TOKEN_EXPIRE_MINUTES
// (60 min côté backend) pour éviter un mint par rendu sans laisser vivre des
// URLs indéfiniment si la session reste ouverte. La revalidation est faite à
// chaque montage si le cache est périmé.
const CACHE_TTL_MS = 50 * 60 * 1000;
const cache = new Map();

export default function useSignedMediaUrl(pathLike) {
  const [url, setUrl] = useState(() => {
    if (!pathLike) return null;
    const hit = cache.get(pathLike);
    if (hit && Date.now() - hit.at < CACHE_TTL_MS) return hit.url;
    return null;
  });

  useEffect(() => {
    if (!pathLike) {
      setUrl(null);
      return undefined;
    }
    const hit = cache.get(pathLike);
    if (hit && Date.now() - hit.at < CACHE_TTL_MS) {
      setUrl(hit.url);
      return undefined;
    }
    let active = true;
    apiService
      .mediaUrl(pathLike)
      .then((signed) => {
        if (!active || !signed) return;
        cache.set(pathLike, { url: signed, at: Date.now() });
        setUrl(signed);
      })
      .catch(() => {});
    return () => {
      active = false;
    };
  }, [pathLike]);

  return url;
}