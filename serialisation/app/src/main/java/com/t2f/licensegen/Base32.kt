package com.t2f.licensegen

import java.io.ByteArrayOutputStream

/**
 * Encodage/décodage Base32 (RFC 4648, sans padding) — nécessaire pour être
 * bit à bit identique à l'outil de référence Python.
 */
object Base32 {

    private const val ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567"

    fun encode(data: ByteArray): String {
        val out = StringBuilder((data.size * 8 + 4) / 5)
        var buffer = 0
        var bitsLeft = 0
        for (b in data) {
            buffer = ((buffer shl 8) or (b.toInt() and 0xFF)) and 0xFFFFFFFF.toInt()
            bitsLeft += 8
            while (bitsLeft >= 5) {
                out.append(ALPHABET[(buffer ushr (bitsLeft - 5)) and 0x1F])
                bitsLeft -= 5
            }
        }
        if (bitsLeft > 0) {
            out.append(ALPHABET[(buffer shl (5 - bitsLeft)) and 0x1F])
        }
        return out.toString()
    }

    fun decode(text: String): ByteArray {
        val cleaned = text.uppercase().filter { it in 'A'..'Z' || it in '2'..'7' }
        val out = ByteArrayOutputStream()
        var buffer = 0
        var bitsLeft = 0
        for (ch in cleaned) {
            if (bitsLeft > 32) throw IllegalArgumentException("Entrée Base32 trop longue")
            buffer = ((buffer shl 5) or (ALPHABET.indexOf(ch) and 0x1F)) and 0xFFFFFFFF.toInt()
            bitsLeft += 5
            if (bitsLeft >= 8) {
                out.write((buffer ushr (bitsLeft - 8)) and 0xFF)
                bitsLeft -= 8
            }
        }
        if (bitsLeft > 0 && (((buffer shl (8 - bitsLeft)) and 0xFF) and ((1 shl (8 - bitsLeft)) - 1) != 0)) {
            throw IllegalArgumentException("Caractères de remplissage invalides.")
        }
        return out.toByteArray()
    }
}