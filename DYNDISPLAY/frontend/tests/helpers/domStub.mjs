/**
 * Stubs DOM minimaux pour charger `services/api.js` hors navigateur.
 * Node n'a ni window ni localStorage, or api.js les utilise.
 */
export function installDomStubs() {
  if (!globalThis.window) {
    globalThis.window = {
      crypto: { randomUUID: () => '00000000-0000-4000-8000-000000000000' },
      localStorage: globalThis.localStorage,
    };
  }
  if (!globalThis.localStorage) {
    const mem = new Map();
    globalThis.localStorage = {
      getItem: (k) => (mem.has(k) ? mem.get(k) : null),
      setItem: (k, v) => mem.set(k, String(v)),
      removeItem: (k) => mem.delete(k),
      clear: () => mem.clear(),
      get length() { return mem.size; },
      key: (i) => Array.from(mem.keys())[i] ?? null,
    };
  }
}
