package com.t2f.licensegen

import java.security.MessageDigest
import javax.crypto.Mac
import javax.crypto.spec.SecretKeySpec

data class LicenseInfo(
    val clientCode: String,
    val sites: Int,
    val posts: Int,
)

/**
 * Génération et validation des codes de licence.
 *
 * Algorithme (identique bit à bit à l'outil de référence Python et au
 * backend FastAPI) :
 *
 *   payload   = "CODE_CLIENT:NOMBRE_SITES:NOMBRE_POSTES"   (UTF-8)
 *   signature = HMAC-SHA256(LICENSE_SECRET, payload) → 8 premiers octets
 *   combined  = payload_bytes + signature_bytes (8 octets)
 *   code      = Base32(combined) (RFC 4648, sans padding), formaté en blocs
 *               de 5 caractères séparés par des tirets.
 */
object LicenseManager {

    const val SIGNATURE_BYTES = 8
    private const val BLOCK_SIZE = 5

    fun generate(clientCode: String, sites: Int, posts: Int): String {
        val payload = "$clientCode:$sites:$posts"
        val payloadBytes = payload.toByteArray(Charsets.UTF_8)
        val signature = sign(payloadBytes)
        val combined = payloadBytes + signature
        val encoded = Base32.encode(combined)
        return encoded.chunked(BLOCK_SIZE).joinToString("-")
    }

    /** Retourne les informations décodées si le code est valide, sinon null. */
    fun validate(code: String): LicenseInfo? {
        val cleaned = code.replace("-", "").trim()
        if (cleaned.isEmpty()) return null
        val combined = try {
            Base32.decode(cleaned)
        } catch (e: IllegalArgumentException) {
            return null
        }
        if (combined.size < SIGNATURE_BYTES) return null

        val payloadBytes = combined.copyOfRange(0, combined.size - SIGNATURE_BYTES)
        val receivedSignature = combined.copyOfRange(combined.size - SIGNATURE_BYTES, combined.size)
        val expectedSignature = sign(payloadBytes)

        if (!MessageDigest.isEqual(expectedSignature, receivedSignature)) return null

        val payload = String(payloadBytes, Charsets.UTF_8)
        val parts = payload.split(":")
        if (parts.size != 3) return null

        val sites = parts[1].toIntOrNull() ?: return null
        val posts = parts[2].toIntOrNull() ?: return null
        if (parts[0].isEmpty() || sites < 0 || posts < 0) return null
        return LicenseInfo(clientCode = parts[0], sites = sites, posts = posts)
    }

    private fun sign(payloadBytes: ByteArray): ByteArray {
        val mac = Mac.getInstance("HmacSHA256")
        mac.init(SecretKeySpec(LicenseConfig.LICENSE_SECRET.toByteArray(Charsets.UTF_8), "HmacSHA256"))
        val full = mac.doFinal(payloadBytes)
        return full.copyOf(SIGNATURE_BYTES)
    }
}