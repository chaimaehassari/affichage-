import { useEffect, useState } from 'react';
import { apiService } from '../services/api';

// Cache mémoire des URL signées, avec TTL en deçà de MEDIA_TOKEN_EXPIRE_MINUTES
// (60 min côté backend) pour éviter un mint par rendu sans laisser vivre des
// URLs indéfiniment si la session reste ouverte. La revalidation est faite à
// chaque montage si le cache est périmé.
const CACHE_TTL_MS = 50 * 60 * 1000;
const cache = new Map();

// Le navigateur n'autorise que ~6 requêtes HTTP simultanées par origine
// (HTTP/1.1). Une galerie de plusieurs centaines de vignettes montait
// autant de hooks en même temps, ce qui saturait la pile réseau
// (net::ERR_INSUFFICIENT_RESOURCES sur POST /media-token). Les mints sont
// donc sérialisés dans une file d'attente unique et bornée.
const MINT_CONCURRENCY = 3;
const MINT_QUEUE_DELAY_MS = 60;

let activeMints = 0;
const pending = [];

function scheduleMint(pathLike, resolve) {
  const run = () => {
    activeMints += 1;
    apiService
      .mediaUrl(pathLike)
      .then((signed) => resolve(signed || null))
      .catch(() => resolve(null))
      .finally(() => {
        activeMints -= 1;
        const next = pending.shift();
        if (next) setTimeout(next.run, MINT_QUEUE_DELAY_MS);
      });
  };

  if (activeMints < MINT_CONCURRENCY) {
    run();
  } else {
    pending.push({ run });
  }
}

// Dédoublonnage : deux vignettes du même fichier partageront un seul mint.
const inflight = new Map();

function mintOnce(pathLike) {
  const existing = inflight.get(pathLike);
  if (existing) return existing;
  const promise = new Promise(resolve => scheduleMint(pathLike, resolve));
  inflight.set(pathLike, promise);
  promise.then(() => inflight.delete(pathLike));
  return promise;
}

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
    mintOnce(pathLike).then((signed) => {
      if (!active || !signed) return;
      cache.set(pathLike, { url: signed, at: Date.now() });
      setUrl(signed);
    });
    return () => {
      active = false;
    };
  }, [pathLike]);

  return url;
}
