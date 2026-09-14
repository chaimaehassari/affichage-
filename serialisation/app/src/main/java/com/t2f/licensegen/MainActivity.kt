package com.t2f.licensegen

import android.content.ClipData
import android.content.ClipboardManager
import android.content.Context
import android.os.Bundle
import android.view.View
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import com.google.android.material.button.MaterialButton
import com.google.android.material.textfield.TextInputEditText
import com.google.android.material.textfield.TextInputLayout
import com.t2f.licensegen.R

class MainActivity : AppCompatActivity() {

    private lateinit var etCode: TextInputEditText
    private lateinit var etSites: TextInputEditText
    private lateinit var etPosts: TextInputEditText
    private lateinit var tvResult: View
    private lateinit var btnCopy: MaterialButton
    private lateinit var etCodeToCheck: TextInputEditText
    private lateinit var tvDecodeResult: View

    private var lastGenerated: String? = null

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)

        etCode = findViewById(R.id.et_code)
        etSites = findViewById(R.id.et_sites)
        etPosts = findViewById(R.id.et_posts)
        tvResult = findViewById(R.id.tv_result)
        btnCopy = findViewById(R.id.btn_copy)
        etCodeToCheck = findViewById(R.id.et_code_to_check)
        tvDecodeResult = findViewById(R.id.tv_decode_result)

        findViewById<MaterialButton>(R.id.btn_generate).setOnClickListener { onGenerate() }
        btnCopy.setOnClickListener { onCopy() }
        findViewById<MaterialButton>(R.id.btn_validate).setOnClickListener { onValidate() }
    }

    private fun onGenerate() {
        clearErrors()

        val code = etCode.text?.toString()?.trim().orEmpty()
        val sites = parsePositiveInt(etSites)
        val posts = parsePositiveInt(etPosts)

        if (code.isEmpty()) {
            errorOn(R.id.til_code, getString(R.string.err_code_required))
            return
        }
        if (sites == null) {
            errorOn(R.id.til_sites, getString(R.string.err_sites_required))
            return
        }
        if (posts == null) {
            errorOn(R.id.til_posts, getString(R.string.err_posts_required))
            return
        }

        val generated = LicenseManager.generate(code, sites, posts)
        lastGenerated = generated

        setText(R.id.tv_result, generated)
        tvResult.visibility = View.VISIBLE
        btnCopy.visibility = View.VISIBLE
    }

    private fun onCopy() {
        val code = lastGenerated ?: return
        val clipboard = getSystemService(Context.CLIPBOARD_SERVICE) as ClipboardManager
        clipboard.setPrimaryClip(ClipData.newPlainText("licence", code))
        Toast.makeText(this, R.string.copied, Toast.LENGTH_SHORT).show()
    }

    private fun onValidate() {
        val input = etCodeToCheck.text?.toString()?.trim().orEmpty()
        val info = LicenseManager.validate(input)
        if (info == null) {
            setText(R.id.tv_decode_result, getString(R.string.decode_invalid))
            findViewById<View>(R.id.tv_decode_result).setBackgroundColor(
                android.graphics.Color.parseColor("#3B0000")
            )
        } else {
            setText(R.id.tv_decode_result, getString(R.string.decode_valid, info.clientCode, info.sites, info.posts))
            findViewById<View>(R.id.tv_decode_result).setBackgroundColor(
                android.graphics.Color.parseColor("#003B00")
            )
        }
        tvDecodeResult.visibility = View.VISIBLE
    }

    private fun parsePositiveInt(field: TextInputEditText): Int? =
        field.text?.toString()?.trim()?.toIntOrNull()?.takeIf { it >= 0 }

    private fun errorOn(layoutId: Int, message: String) {
        findViewById<TextInputLayout>(layoutId).error = message
    }

    private fun clearErrors() {
        findViewById<TextInputLayout>(R.id.til_code).error = null
        findViewById<TextInputLayout>(R.id.til_sites).error = null
        findViewById<TextInputLayout>(R.id.til_posts).error = null
    }

    private fun setText(viewId: Int, text: String) {
        findViewById<android.widget.TextView>(viewId).text = text
    }
}