/**
 * Hook de résolution : si un import relatif ne pointe pas vers un fichier
 * existant, on réessaie avec `.js` puis `/index.js` (conventions Vite).
 */
import { existsSync } from 'node:fs';
import { fileURLToPath, pathToFileURL } from 'node:url';

export async function resolve(specifier, context, nextResolve) {
  try {
    return await nextResolve(specifier, context);
  } catch (err) {
    if (!specifier.startsWith('.') && !specifier.startsWith('/')) throw err;

    const base = context.parentURL
      ? new URL(specifier, context.parentURL)
      : pathToFileURL(specifier);
    const basePath = fileURLToPath(base);
    if (existsSync(basePath)) throw err;

    for (const candidate of [`${basePath}.js`, `${basePath}/index.js`]) {
      if (existsSync(candidate)) {
        return nextResolve(pathToFileURL(candidate).href, context);
      }
    }
    throw err;
  }
}
