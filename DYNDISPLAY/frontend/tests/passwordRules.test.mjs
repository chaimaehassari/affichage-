/**
 * Non-regression : la politique de mot de passe du frontend est identique a
 * celle du backend.
 *
 * Contexte : aucun ecran de saisie ne montrait les regles. Un mot de passe
 * hors politique partait donc en HTTP 422, affiche comme
 * « Value error, new_password ... » — un echec de serveur sur un simple
 * formulaire. Ces tests verrouillent le doublon `src/utils/passwordRules.js`
 * contre les memes seuils que les validators Python :
 *   backend/app/schemas/settings.py  ChangePasswordRequest
 *   backend/app/schemas/auth.py      UserCreateRequest / PasswordResetRequest
 *
 * Si une regle change d'un cote, ces tests echouent : le formulaire ne peut
 * plus accepter en silence un mot de passe que le backend refusera.
 */
import test from 'node:test';
import assert from 'node:assert/strict';

const url = new URL('../src/utils/passwordRules.js', import.meta.url);
const mod = await import(`${url.href}?t=${Date.now()}${Math.random()}`);
const { validatePassword, checkPasswordRules, PASSWORD_MIN_LENGTH, PASSWORD_MAX_LENGTH } = mod;

test('les seuils sont 8 a 14 caracteres', () => {
  assert.equal(PASSWORD_MIN_LENGTH, 8);
  assert.equal(PASSWORD_MAX_LENGTH, 14);
});

test('un mot de passe valide passe', () => {
  for (const pw of ['Dyn2026!', 'a1!bcdef', 'Aa1!aaaa', 'Dyn2026a!']) {
    assert.equal(validatePassword(pw), null, `attendu valide : ${pw}`);
  }
});

test('le mot de passe genere par install.bat est rejete comme tout le reste', () => {
  // Regression documentee. install.bat ecrit dans admin-credentials.txt un
  // mot de passe = JJMMAAAA + SUPREME_ADMIN_SECRET, le secret etant
  // alphanumerique. Exemple reel : `05102026X7K9`.
  //   -> 12 caracteres : longueur OK
  //   -> X, K        : une lettre OK
  //   -> 0,5,1...    : un chiffre OK
  //   -> aucun `!@#$...` : PAS de caractere special
  // Le backend REJETTE donc ce mot de passe (verifie avec le validator
  // Python, pas seulement avec ce doublon JS). Sans consequence en pratique
  // parce que `must_change_password` force un choix a la premiere connexion,
  // mais l'installeur produit un secret que sa propre politique refuse.
  assert.match(validatePassword('05102026X7K9'), /caractère spécial/);
});

test('la longueur est bornee dans les deux sens', () => {
  // 7 caracteres : trop court.
  assert.match(validatePassword('Ab1!def'), /entre 8 et 14/);
  // 15 caracteres : trop long. C'est le piege le plus frequent : une
  // passphrase naturelle est refusee sans que rien ne l'annonce.
  assert.match(validatePassword('Aa1!' + 'x'.repeat(11)), /entre 8 et 14/);
  // 8 et 14 exactes : les deux bornes sont acceptes.
  assert.equal(validatePassword('Ab1!defg'), null);
  assert.equal(validatePassword('Ab1!' + 'x'.repeat(10)), null);
});

test('il faut au moins une lettre, un chiffre et un special', () => {
  assert.match(validatePassword('1234567!'), /une lettre/);
  assert.match(validatePassword('abcdefg!'), /un chiffre/);
  assert.match(validatePassword('abcdefg1'), /caractère spécial/);
});

test('chaque special accepte par le backend est accepte ici', () => {
  const speciaux = '!@#$%^&*(),.?":{}|<>-_=+[]\\;\'`~';
  for (const c of speciaux) {
    const pw = `Abcdef1${c}`;
    assert.equal(validatePassword(pw), null, `special refuse : ${JSON.stringify(c)}`);
  }
});

test('le vide est refuse avec le message de l ecran', () => {
  assert.equal(validatePassword(''), 'Le mot de passe est obligatoire.');
  assert.equal(
    validatePassword('', 'Le nouveau mot de passe est obligatoire.'),
    'Le nouveau mot de passe est obligatoire.'
  );
});

test('la premiere regle violee est celle signalee, comme en Python', () => {
  // 4 caracteres, sans lettre ni chiffre : la longueur gagne, car c'est
  // le premier test du validator backend.
  assert.match(validatePassword('!!!!'), /entre 8 et 14/);
  // 8 caracteres, uniquement des speciaux : la longueur est bonne, la
  // lettre est donc la premiere regle violee.
  assert.match(validatePassword('!!!!!!!!'), /une lettre/);
  // 8 caracteres, lettres + speciaux, sans chiffre.
  assert.match(validatePassword('abcdefg!'), /un chiffre/);
});

test('checkPasswordRules detaille les quatre regles', () => {
  assert.deepEqual(checkPasswordRules('Dyn2026!'), {
    length: true, letter: true, digit: true, special: true,
  });
  // 8 caracteres, sans caractere special : une seule regle manque.
  assert.deepEqual(checkPasswordRules('Dyn2026a'), {
    length: true, letter: true, digit: true, special: false,
  });
  // 7 caracteres : la longueur manque aussi.
  assert.deepEqual(checkPasswordRules('Dyn2026'), {
    length: false, letter: true, digit: true, special: false,
  });
  assert.deepEqual(checkPasswordRules(''), {
    length: false, letter: false, digit: false, special: false,
  });
});
