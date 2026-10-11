/*
 * Harnais de test du one-shot player (src/reboot/rebootOnce.js).
 *
 * Le player n'a ni vitest ni jest et son package.json est en CommonJS
 * (electron/main.js utilise require) : on ne peut donc pas importer le module
 * ESM directement depuis node. On lit la source, on retire les `export`, et on
 * évalue le résultat — les fonctions testées sont pures, sans import ni
 * dépendance à Electron.
 *
 * Cible : rebootOnce.js (ponctuel). Ne teste PAS rebootScheduler.js (récurrent),
 * volontairement laissé intact.
 */
const fs = require('fs');
const path = require('path');
const vm = require('vm');

// Le dépôt est multi-projets : on remonte depuis tests/js/ jusqu'à trouver le
// player plutôt que de coder en dur un nombre de niveaux.
function locatePlayerSource() {
  const rel = path.join('dyndisplay-windows-player', 'src', 'reboot', 'rebootOnce.js');
  let dir = __dirname;
  for (let i = 0; i < 8; i += 1) {
    const candidate = path.join(dir, rel);
    if (fs.existsSync(candidate)) return candidate;
    dir = path.dirname(dir);
  }
  throw new Error('rebootOnce.js introuvable depuis ' + __dirname);
}

const SRC = locatePlayerSource();

const stripped = fs.readFileSync(SRC, 'utf8').replace(/^export\s+/gm, '');
// Les `const` de premier niveau restent dans la portée lexicale du contexte :
// on expose explicitement les deux fonctions pures testées.
const code = `${stripped}\n;globalThis.__api = { normalizeInstant, shouldRunOnce, runRebootOnce };`;
const sandbox = { module: { exports: {} }, console, Date, Math, Number, JSON };
vm.createContext(sandbox);
vm.runInContext(code, sandbox);
const { shouldRunOnce, normalizeInstant, runRebootOnce } = sandbox.__api;

let failures = 0;
function check(label, cond, extra) {
  if (cond) {
    console.log(`  ok   ${label}`);
  } else {
    failures += 1;
    console.log(`  FAIL ${label}${extra ? ' -> ' + JSON.stringify(extra) : ''}`);
  }
}

// Deux one-shots le même jour : 10:00 et 16:00.
const T10 = '2030-06-15T10:00:00+00:00';
const T16 = '2030-06-15T16:00:00+00:00';
const ms10 = Date.parse(T10);
const ms16 = Date.parse(T16);
const ISO10 = new Date(ms10).toISOString();

console.log('normalizeInstant');
check('ISO valide -> ms', normalizeInstant(T10) === ms10);
check('absent -> null', normalizeInstant(null) === null && normalizeInstant('') === null);
check('format invalide -> null', normalizeInstant('25:00') === null && normalizeInstant('hier') === null);

console.log('shouldRunOnce — déclenchement');
check('pas de cible -> no-target', shouldRunOnce({ rebootOnceAt: null }).reason === 'no-target');
check('cible non atteinte -> not-due', shouldRunOnce({ rebootOnceAt: T10, now: ms10 - 1000 }).reason === 'not-due');
check('cible atteinte + état vierge -> run',
  shouldRunOnce({ rebootOnceAt: T10, lastRebootAt: null, now: ms10 + 1000 }).run === true);
check('pile à l\'instant -> run',
  shouldRunOnce({ rebootOnceAt: T10, lastRebootAt: null, now: ms10 }).run === true);

console.log('shouldRunOnce — anti-boucle par INSTANT (lastRebootAt)');
check('même instant déjà consommé -> already-done',
  shouldRunOnce({ rebootOnceAt: T10, lastRebootAt: ISO10, now: ms10 + 60000 }).reason === 'already-done');
check('relecture de config après reboot -> pas de second reboot',
  shouldRunOnce({ rebootOnceAt: T10, lastRebootAt: ISO10, now: ms10 + 3600000 }).run === false);

console.log('shouldRunOnce — deux one-shots le MÊME JOUR');
// C'est précisément le cas que lastRebootDate (clé de date) ne sait pas gérer.
const apres10 = shouldRunOnce({ rebootOnceAt: T16, lastRebootAt: ISO10, now: ms16 });
check('16:00 se déclenche même si 10:00 a déjà eu lieu', apres10.run === true, apres10);
check('et son instant est bien 16:00', apres10.iso === new Date(ms16).toISOString());
const memeJourDate = { rebootOnceAt: T16, lastRebootAt: '2030-06-15', now: ms16 };
check('une clé de date ne suffirait pas (référence du défaut)',
  shouldRunOnce(memeJourDate).run === true, memeJourDate);

console.log('shouldRunOnce — pas d\'interférence avec le récurrent');
// lastRebootDate est la clé du récurrent : le one-shot ne doit ni l'écraser
// ni en dépendre. lastRebootAt non vide ne doit pas non plus neutraliser
// une nouvelle cible.
check('lastRebootDate du jour ne bloque pas le one-shot',
  shouldRunOnce({ rebootOnceAt: T10, lastRebootAt: '2030-06-15', now: ms10 + 1000 }).run === true);
check('lastRebootAt non vide ne bloque pas une autre cible',
  shouldRunOnce({ rebootOnceAt: T16, lastRebootAt: ISO10, now: ms16 }).run === true);

// ── runRebootOnce : verrou d'anti-double-exécution ──────────────────────────
// Le chargement initial ET la première synchro appellent le one-shot presque en
// même temps. Sans verrou posé AVANT le premier await, les deux appels lisent
// l'état avant que l'un n'écrive lastRebootAt et déclenchent deux reboot.
// On reproduit la course avec un getState volontairement lent.
async function testInFlightGuard() {
  console.log('runRebootOnce — anti-double-exécution');
  const calls = { getState: 0, setState: 0, execute: 0 };
  let written = null;
  // Date passée : le one-shot est dû.
  const DUE = new Date(Date.parse('2020-01-01T00:00:00Z') - 1000).toISOString();

  sandbox.window = {
    dyndisplay: {
      reboot: {
        async getState() {
          calls.getState += 1;
          await new Promise((r) => setTimeout(r, 20)); // laisse la course s'ouvrir
          return { lastRebootDate: '2030-06-15' }; // aucun lastRebootAt
        },
        async setState(next) {
          calls.setState += 1;
          written = next;
        },
        async execute() {
          calls.execute += 1;
          return { ok: true };
        },
      },
    },
  };

  const getConfig = () => ({ reboot_once_at: DUE });
  const [a, b] = await Promise.all([
    runRebootOnce({ getConfig }),
    runRebootOnce({ getConfig }),
  ]);

  check('un seul execute() pour deux appels concurrents', calls.execute === 1, calls);
  check('le perdant renvoie in-flight',
    [a, b].some((r) => r.reason === 'in-flight'), { a: a.reason, b: b.reason });
  check('lastRebootAt écrit avant le shutdown', calls.setState === 1 && written.lastRebootAt != null, written);
  check('lastRebootDate du récurrent préservé', written.lastRebootDate === '2030-06-15', written);

  // Verrou relâché : un appel ultérieur doit pouvoir réévaluer (et ne pas
  // rester bloqué par le chemin 'no-target').
  delete sandbox.window;
  const apres = await runRebootOnce({ getConfig: () => ({}) });
  check('verrou relâché après l\'exécution', apres.reason === 'no-target', apres);
}

testInFlightGuard().then(() => {
  console.log(`\n${failures === 0 ? 'PLAYER ONESHOT OK' : 'PLAYER ONESHOT FAILURES: ' + failures}`);
  process.exit(failures === 0 ? 0 : 1);
});
