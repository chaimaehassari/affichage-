package com.t2f.licensegen

/**
 * Configuration de génération des licences.
 *
 * Le secret est injecté au moment du build depuis `local.properties`
 * (`license.secret`), qui est exclu de Git. Il NE DOIT PAS être en dur ici.
 *
 * CE SECRET DOIT ÊTRE IDENTIQUE À CELUI UTILISÉ :
 *  1) côté serveur / backend FastAPI qui valide les codes, et
 *  2) dans l'outil de référence Python existant.
 *
 * ⚠️ SÉCURITÉ : le secret est embarqué dans l'APK (outil interne, hors-ligne).
 * Un APK peut être décompilé et le secret extrait. Ne JAMAIS publier cette
 * app sur le Play Store — installation uniquement par sideload sur les
 * téléphones internes T2F.
 */
object LicenseConfig {
    const val LICENSE_SECRET: String = BuildConfig.LICENSE_SECRET
}