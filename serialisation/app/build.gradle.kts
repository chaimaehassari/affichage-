import java.util.Properties

plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

// Le secret de licence vit UNIQUEMENT dans local.properties (exclu de Git).
// https://developer.android.com/studio/build/gradle-tips#basics
val localProperties = Properties().apply {
    val file = rootProject.file("local.properties")
    if (file.exists()) file.inputStream().use(::load)
}
val licenseSecret: String = localProperties.getProperty("license.secret")?.trim().orEmpty()
if (licenseSecret.isEmpty()) {
    throw GradleException(
        "license.secret absent de local.properties. Copier local.properties.example " +
        "vers local.properties et y mettre la même valeur que LICENSE_SECRET du backend."
    )
}
if (licenseSecret == "REMPLACER-PAR-LE-VRAI-SECRET") {
    throw GradleException("license.secret dans local.properties est encore le placeholder : remplacer par la vraie valeur.")
}

android {
    namespace = "com.t2f.licensegen"
    compileSdk = 34

    defaultConfig {
        applicationId = "com.t2f.licensegen"
        minSdk = 21
        targetSdk = 34
        versionCode = 1
        versionName = "1.0"
        testInstrumentationRunner = "androidx.test.runner.AndroidJUnitRunner"
        buildConfigField("String", "LICENSE_SECRET", "\"$licenseSecret\"")
    }

    buildFeatures {
        buildConfig = true
    }

    buildTypes {
        release {
            isMinifyEnabled = true
            proguardFiles(
                getDefaultProguardFile("proguard-android-optimize.txt"),
                "proguard-rules.pro"
            )
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    kotlinOptions {
        jvmTarget = "17"
    }
}

dependencies {
    implementation("androidx.core:core-ktx:1.13.1")
    implementation("androidx.appcompat:appcompat:1.7.0")
    implementation("com.google.android.material:material:1.12.0")
    implementation("androidx.constraintlayout:constraintlayout:2.1.4")

    testImplementation("junit:junit:4.13.2")
}