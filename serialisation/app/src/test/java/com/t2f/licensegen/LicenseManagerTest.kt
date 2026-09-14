package com.t2f.licensegen

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Test

class LicenseManagerTest {

    @Test
    fun generateThenValidateImmediately_succeeds() {
        val code = LicenseManager.generate("12345678", 12, 34)
        val info = LicenseManager.validate(code)
        assertNotNull("Le code généré doit être revalidé avec succès", info)
        assertEquals("12345678", info!!.clientCode)
        assertEquals(12, info.sites)
        assertEquals(34, info.posts)
    }

    @Test
    fun tamperSingleCharacter_isRejected() {
        val code = LicenseManager.generate("12345678", 12, 34)
        val first = code.first()
        val replacement = if (first == 'A') 'B' else 'A'
        val tampered = replacement + code.drop(1)
        assertNull("Un code modifié d'un seul caractère doit être rejeté", LicenseManager.validate(tampered))
    }

    @Test
    fun sameInputs_generateSameCode_deterministic() {
        val a = LicenseManager.generate("9876543", 5, 10)
        val b = LicenseManager.generate("9876543", 5, 10)
        assertEquals("Deux générations avec les mêmes entrées doivent donner le même code", a, b)
    }

    @Test
    fun codeWithDashesAndWithout_isEquivalent() {
        val code = LicenseManager.generate("11111111", 2, 3)
        val withoutDashes = code.replace("-", "")
        val info = LicenseManager.validate(withoutDashes)
        assertNotNull(info)
    }

    @Test
    fun garbageInput_isRejected() {
        assertNull(LicenseManager.validate(""))
        assertNull(LicenseManager.validate("NOT-A-CODE!!"))
        assertNull(LicenseManager.validate("A1B2"))
    }

    @Test
    fun formatUses5CharBlocksWithDashes() {
        val code = LicenseManager.generate("22222222", 9, 9)
        val blocks = code.split("-")
        assert(blocks.isNotEmpty())
        assert(blocks.take(blocks.size - 1).all { it.length == 5 })
        assert(blocks.last().length in 1..5)
    }

    @Test
    fun base32RoundTrip() {
        val original = byteArrayOf(1, 2, 3, 4, 5, 6, 7, 8, 9)
        val encoded = Base32.encode(original)
        val decoded = Base32.decode(encoded)
        assertEquals(original.toList(), decoded.toList())
    }

    @Test
    fun alphanumericClientCode_generateThenValidate() {
        val code = LicenseManager.generate("CLIENT001", 5, 1000)
        val info = LicenseManager.validate(code)
        assertNotNull(info)
        assertEquals("CLIENT001", info!!.clientCode)
        assertEquals(5, info.sites)
        assertEquals(1000, info.posts)
    }
}