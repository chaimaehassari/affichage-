// Politique de mot de passe — MIROIR EXACT de la validation backend.
//
//   backend/app/schemas/settings.py  ChangePasswordRequest.validate_new_password
//   backend/app/schemas/auth.py      UserCreateRequest.validate_password
//                                     PasswordResetRequest.validate_password
//
// Pourquoi un duplicat ici alors que la source de vérité est le backend :
// sans contrôle local, un mot de passe hors politique part en HTTP 422 et
// l'utilisateur voit un échec de serveur sur un simple formulaire. Le contrôle
// local ne REMPLACE pas le backend (il reste seul juge, et ses messages
// prévalent) ; il évite juste l'aller-retour et rend la règle visible.
//
// Toute divergence entre ce fichier et les validators Python se paie
// immediatement : un mot de passe accepté ici mais refuse la bas produit un
// 422 que le formulaire ne peut plus expliquer. Modifier les deux ensemble.
export const PASSWORD_MIN_LENGTH = 8;
export const PASSWORD_MAX_LENGTH = 14;

// Même classe de caractères que le backend : `!@#$%^&*(),.?":{}|<>_-=+[]\;\`'~`
const SPECIAL_CHAR = /[!@#$%^&*(),.?":{}|<>\-_=+\[\]\\;'`~]/;

// Libellés affichés, dans l'ordre des contrôles backend.
export const PASSWORD_RULES = [
  { key: 'length', label: `Entre ${PASSWORD_MIN_LENGTH} et ${PASSWORD_MAX_LENGTH} caractères` },
  { key: 'letter', label: 'Au moins une lettre' },
  { key: 'digit', label: 'Au moins un chiffre' },
  { key: 'special', label: 'Au moins un caractère spécial (!@#$%^&*...)' },
];

export const LENGTH_RULE_MESSAGE =
  `Le mot de passe doit contenir entre ${PASSWORD_MIN_LENGTH} et ${PASSWORD_MAX_LENGTH} caractères.`;

export const SPECIAL_RULE_MESSAGE =
  'Le mot de passe doit contenir au moins un caractère spécial.';

/**
 * État règle par règle, pour afficher des coches en direct.
 * @returns {{length: boolean, letter: boolean, digit: boolean, special: boolean}}
 */
export function checkPasswordRules(value) {
  const v = value || '';
  return {
    length: v.length >= PASSWORD_MIN_LENGTH && v.length <= PASSWORD_MAX_LENGTH,
    letter: /[A-Za-z]/.test(v),
    digit: /\d/.test(v),
    special: SPECIAL_CHAR.test(v),
  };
}

/**
 * Message de refus, dans l'ORDRE des validators backend (première règle
 * violée gagne), ou null si le mot de passe est acceptable.
 *
 * `requiredMessage` permet de reprendre la formulation de chaque écran
 * (« Le nouveau mot de passe est obligatoire. » côté changement de mot de
 * passe, « Le mot de passe est obligatoire. » ailleurs).
 */
export function validatePassword(value, requiredMessage = 'Le mot de passe est obligatoire.') {
  const v = value || '';
  if (!v) return requiredMessage;

  const checks = checkPasswordRules(v);
  if (!checks.length) return LENGTH_RULE_MESSAGE;
  if (!checks.letter) return 'Le mot de passe doit contenir au moins une lettre.';
  if (!checks.digit) return 'Le mot de passe doit contenir au moins un chiffre.';
  if (!checks.special) return SPECIAL_RULE_MESSAGE;
  return null;
}
