// Limiteur de concurrence pour les appels HTTP.
//
// Le navigateur n'autorise que ~6 connexions simultinees par origine en
// HTTP/1.1. Envoyer N requetes d'un coup (un groupe -> ses posts + sa
// hierarchie media, un poste -> son etat de sync, ...) provoque
// net::ERR_INSUFFICIENT_RESOURCES et fait echouer silencieusement une
// partie des appels.
//
// `mapWithConcurrency`execute une liste d'appels asynchrones par lots de
// `limit`, avec une courte pause entre deux lots pour laisser respirer le
// serveur. L'ordre des resultats est preserve.
const DEFAULT_LIMIT = 6;
const DEFAULT_PAUSE_MS = 60;

const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));

export async function mapWithConcurrency(
  items,
  worker,
  { limit = DEFAULT_LIMIT, pauseMs = DEFAULT_PAUSE_MS } = {},
) {
  const list = Array.from(items);
  const out = new Array(list.length);
  const width = Math.max(1, Math.min(limit, list.length));

  for (let i = 0; i < list.length; i += width) {
    const batch = list.slice(i, i + width);
    const results = await Promise.all(batch.map((item, idx) => worker(item, i + idx)));
    results.forEach((value, idx) => { out[i + idx] = value; });
    if (i + width < list.length && pauseMs > 0) {
      await sleep(pauseMs);
    }
  }
  return out;
}
