# United Mobile EPOS — Android APK Build Guide

**App:** UnitedMobileApp  
**React Native:** 0.73.6  
**Package ID:** com.unitedmobileapp  
**Last updated:** May 2026

---

## Prerequisites — What You Need to Install

Do these **once** on your development PC. Skip anything already installed.

---

### 1. Node.js (v18 LTS or newer)

1. Go to **https://nodejs.org**
2. Download the **LTS** version (green button)
3. Run the installer — accept all defaults
4. Verify:
   ```
   node --version     (should show v18.x.x or higher)
   npm --version      (should show 9.x.x or higher)
   ```

---

### 2. Java Development Kit (JDK 17)

React Native 0.73.x requires **JDK 17 exactly** (not 11, not 21).

1. Go to **https://adoptium.net/temurin/releases/**
2. Filter: Version = **17**, OS = **Windows**, Architecture = **x64**, Package = **JDK**
3. Download the `.msi` installer and run it
4. During installation, tick **"Set JAVA_HOME variable"**
5. Verify:
   ```
   java -version      (should show openjdk version "17.x.x")
   ```

---

### 3. Android Studio

1. Go to **https://developer.android.com/studio**
2. Download and run the installer — accept all defaults
3. On first launch, the **Android Studio Setup Wizard** runs automatically:
   - Choose **Standard** installation
   - Accept all license agreements
   - Wait for SDK download to complete (may take 10–15 minutes)
4. After setup, note the **Android SDK Location** — you will need it in the next step.
   - Default location: `C:\Users\YourName\AppData\Local\Android\Sdk`
   - To find it: Android Studio → Settings → Appearance & Behavior → System Settings → Android SDK

---

### 4. Set the ANDROID_HOME Environment Variable

1. Press **Win + S** → type **"Environment Variables"** → click **"Edit the system environment variables"**
2. Click **"Environment Variables…"** button
3. Under **"User variables"**, click **New**:
   - Variable name:  `ANDROID_HOME`
   - Variable value: `C:\Users\YourName\AppData\Local\Android\Sdk`
   *(Use your actual SDK path from Step 3)*
4. Still under "User variables", find **Path** → click **Edit** → **New**, add:
   ```
   %ANDROID_HOME%\platform-tools
   %ANDROID_HOME%\emulator
   ```
5. Click OK on all dialogs
6. **Close and reopen** any terminal windows so the new variables take effect
7. Verify:
   ```
   adb --version      (should show Android Debug Bridge version x.x.x)
   ```

---

## Building the APK

Open a **Command Prompt** or **PowerShell** window in the app folder.

---

### Step 1 — Install JavaScript dependencies

```
cd E:\ShopSoftware\mobile_app\UnitedMobileApp
npm install
```

This downloads all packages listed in `package.json` into the `node_modules\` folder.  
Takes 1–3 minutes on first run. Safe to run again — it is idempotent.

---

### Step 2 — Build the Release APK

```
cd android
gradlew assembleRelease
```

- First run downloads Gradle and compiles everything — can take **5–15 minutes**
- Subsequent runs are faster (cached)
- Watch for `BUILD SUCCESSFUL` at the end

---

### Step 3 — Find the APK

After a successful build, the APK is at:

```
android\app\build\outputs\apk\release\app-release.apk
```

Full path from ShopSoftware:
```
E:\ShopSoftware\mobile_app\UnitedMobileApp\android\app\build\outputs\apk\release\app-release.apk
```

---

## Installing on the Phone

### Option A — Copy via USB (simplest)

1. Connect the phone to the PC with a USB cable
2. On the phone: swipe down the notification bar → tap **"USB - Charging only"** → change to **"File Transfer"**
3. Open **File Explorer** on the PC → navigate to the phone storage → copy `app-release.apk` to the **Downloads** folder on the phone
4. On the phone: open **Files** app → Downloads → tap `app-release.apk` → Install

> **If "Install blocked":** Go to phone Settings → Security → enable **"Install from unknown sources"**  
> (On Android 8+: Settings → Apps → Special app access → Install unknown apps → Files → Allow)

---

### Option B — Install Directly with ADB (faster for repeated installs)

Connect the phone via USB, enable USB Debugging, then:

**Enable USB Debugging on the phone:**
1. Settings → About phone → tap **Build number** 7 times → "You are now a developer"
2. Settings → Developer options → turn on **USB Debugging**
3. Connect USB → accept the "Allow USB debugging?" prompt on the phone

**Install the APK:**
```
cd E:\ShopSoftware\mobile_app\UnitedMobileApp\android\app\build\outputs\apk\release
adb install app-release.apk
```

Expected output:
```
Performing Streamed Install
Success
```

To reinstall over an existing version:
```
adb install -r app-release.apk
```

---

## Connecting the App to the Shop PC

After installing, the app needs to know the PC's IP address:

1. On the shop PC: open **CMD** → type `ipconfig` → note the **IPv4 Address** (e.g. `192.168.1.5`)
2. Make sure the EPOS desktop app is running (this starts the API server on port 5000 automatically)
3. On the phone: open United Mobile app → tap **Change Server** → enter:
   ```
   http://192.168.1.5:5000
   ```
4. Tap **Test Connection** — should show "Connected"

> **Both the phone and the shop PC must be on the same Wi-Fi network.**  
> The PC's Windows Firewall must allow TCP port 5000.  
> If blocked: Windows Defender Firewall → Allow an app → add `UnitedMobileEPOS.exe` or add a rule for port 5000.

---

## Troubleshooting

| Problem | Fix |
|---|---|
| `gradlew : The term 'gradlew' is not recognized` | Make sure you ran `cd android` first, or use `.\gradlew assembleRelease` in PowerShell |
| `SDK location not found` | Create `android\local.properties` with content: `sdk.dir=C:\\Users\\YourName\\AppData\\Local\\Android\\Sdk` |
| `JAVA_HOME is not set` | Re-do Step 2 (JDK 17), make sure "Set JAVA_HOME" was ticked during install |
| `error Failed to install the app` (ADB) | Re-enable USB Debugging, try a different USB cable, or use Option A |
| `ECONNREFUSED` on phone | EPOS app is not running on PC, or wrong IP address, or not on same Wi-Fi |
| Blank screen after install | Run `adb logcat` to see error; usually a missing permission or wrong server URL |
| `npm install` fails with ENOENT | Delete `node_modules\` folder and run `npm install` again |
| Build fails after pulling new source | Run `cd android && gradlew clean`, then `gradlew assembleRelease` again |

---

## Quick Reference

```
# Install dependencies (first time or after pulling changes)
npm install

# Build release APK
cd android
gradlew assembleRelease

# APK location
android\app\build\outputs\apk\release\app-release.apk

# Install via ADB
adb install -r app-release.apk

# Clean build (if getting strange errors)
gradlew clean
gradlew assembleRelease
```
