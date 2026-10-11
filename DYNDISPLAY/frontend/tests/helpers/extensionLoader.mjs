/**
 * Loader Node : Vite résout les imports sans extension (`../services/api`),
 * Node ESM exige `.js`. Ce hook comble l'écart SANS toucher au code source.
 *
 * Usage : node --import ./tests/helpers/extensionLoader.mjs --test tests/
 */
import { register } from 'node:module';
import { pathToFileURL } from 'node:url';

register('./extensionResolver.mjs', pathToFileURL('./tests/helpers/'));
