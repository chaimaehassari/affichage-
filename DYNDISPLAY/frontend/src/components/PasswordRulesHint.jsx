import { Check, X } from 'lucide-react';
import { PASSWORD_RULES, checkPasswordRules } from '../utils/passwordRules';

/**
 * Rappel de la politique de mot de passe, avec état satisfied par règle.
 *
 * `MustChangePassword` affichait déjà une liste de règles, mais sous forme de
 * texte fixe, et les quatre autres écrans de saisie (Paramètres, création et
 * réinitialisation d'utilisateur, mot de passe oublié) n'affichaient RIEN :
 * l'utilisateur discovert la contrainte en Submit, sous la forme d'un 422
 * interprété comme une panne. Un composant unique évite que les écrans
 * divergent à nouveau.
 *
 * L'état n'est évalué qu'à partir du moment où l'utilisateur a saisi quelque
 * chose : afficher quatre croix sur un formulaire vide est un reproche, pas
 * une aide.
 */
export default function PasswordRulesHint({ value, className = '' }) {
  const touched = Boolean(value);
  const checks = checkPasswordRules(value);

  return (
    <ul className={`mt-2 space-y-1 ${className}`}>
      {PASSWORD_RULES.map((rule) => {
        const ok = checks[rule.key];
        return (
          <li
            key={rule.key}
            className={`flex items-center gap-1.5 text-xs transition-colors ${
              touched
                ? ok
                  ? 'text-emerald-400/90'
                  : 'text-[#a0a7b3]'
                : 'text-[#a0a7b3]'
            }`}
          >
            <span className="w-3.5 shrink-0">
              {touched &&
                (ok ? (
                  <Check className="w-3.5 h-3.5" strokeWidth={3} aria-hidden="true" />
                ) : (
                  <X className="w-3.5 h-3.5 text-[#6b7280]" strokeWidth={3} aria-hidden="true" />
                ))}
            </span>
            {rule.label}
          </li>
        );
      })}
    </ul>
  );
}
