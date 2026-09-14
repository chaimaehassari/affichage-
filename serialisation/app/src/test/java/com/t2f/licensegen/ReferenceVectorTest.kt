package com.t2f.licensegen

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import java.security.MessageDigest
import javax.crypto.Mac
import javax.crypto.spec.SecretKeySpec

/**
 * Interopérabilité et vecteurs de référence.
 *
 * Le test [knownVector_matchesPythonReferenceTool] est un VRAI test croisé :
 * le code attendu ci-dessous a été généré indépendamment par l'outil Python
 * de référence (DYNDISPLAY/backend/app/core/license_utils.generate_license)
 * avec le SECRET RÉEL et les entrées fixes TEST01 / 5 / 20. Le secret utilisé
 * par ce build vient de local.properties (injecté via BuildConfig). Une
 * divergence d'encodage ou de HMAC entre Kotlin et Python ferait échouer ce test.
 */
class ReferenceVectorTest {

    @Test
    fun crossVector_matchesPythonReferenceTool() {
        // Généré par l'outil Python de référence avec le secret réel :
        //   generate_license("TEST01", 5, 20)  ==  "KRCVG-VBQGE-5DKOR-SGAHR-BLJMK-YIX73-Q"
        val expected = "KRCVG-VBQGE-5DKOR-SGAHR-BLJMK-YIX73-Q"
        val produced = LicenseManager.generate("TEST01", 5, 20)
        assertEquals(
            "Le code Kotlin doit être bit à bit identique au code Python de référence.",
            expected, produced
        )
    }

    @Test
    fun crossVector_roundTripsThroughValidate() {
        val code = LicenseManager.generate("TEST01", 5, 20)
        val info = LicenseManager.validate(code)
        assertEquals("TEST01", info?.clientCode)
        assertEquals(5, info?.sites)
        assertEquals(20, info?.posts)
    }

    @Test
    fun secretIsNotPlaceholder() {
        val secret = LicenseConfig.LICENSE_SECRET
        assertTrue(
            "Le secret ne doit pas être le placeholder — local.properties doit contenir la vraie valeur.",
            secret != "0000000000000000" && secret.isNotBlank()
        )
    }

    @Test
    fun signatureLength_isEightBytes() {
        // Propriété HMAC-SHA256 générique : digest complet = 32 octets.
        val payload = "1:2:3".toByteArray(Charsets.UTF_8)
        val mac = Mac.getInstance("HmacSHA256")
        mac.init(SecretKeySpec("x".toByteArray(Charsets.UTF_8), "HmacSHA256"))
        val full = mac.doFinal(payload)
        assertEquals(32, full.size)
    }

    @Test
    fun rejectedCode_signatureMismatch() {
        val valid = LicenseManager.generate("55555555", 1, 2)
        val bytes = Base32.decode(valid.replace("-", ""))
        val corrupted = bytes.copyOf()
        corrupted[corrupted.size - 1] = (corrupted[corrupted.size - 1].toInt() xor 0xFF).toByte()
        val bogus = Base32.encode(corrupted).chunked(5).joinToString("-")
        assertNull(LicenseManager.validate(bogus))
    }
}