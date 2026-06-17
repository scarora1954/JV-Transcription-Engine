@echo off
:: पञ्चमाक्षर नियमों के अनुसार मन्च तैयार किया जा रहा है
title Ngrok Streamlit Tunnel Controller
echo ==================================================
echo       NGROK STREAMLIT TUNNEL PIPELINE
echo ==================================================
echo.

:: 1. अपना NGROK AUTH TOKEN यहाँ दर्ज करें (केवल पहली बार आवश्यक)
:: वेबसाइट से मिला टोकन नीचे उद्धरण चिह्नों (Quotes) के बीच पेस्ट करें
set NGROK_TOKEN="YOUR_NGROK_AUTH_TOKEN_HERE"

:: 2. पहली बार कॉन्फ़िगरेशन सेट करना
if exist "%USERPROFILE%\.config\ngrok\ngrok.yml" (
    echo [INFO] Ngrok config already exists. Proceeding to connect...
) else (
    echo [INBOUND] Configuring Ngrok authentication token...
    ngrok config add-authtoken %NGROK_TOKEN%
)

echo.
echo ==================================================
echo [STATUS] Launching Secure HTTP Tunnel on Port 8501...
echo [NOTICE] Keep this window OPEN while sharing the app!
echo ==================================================
echo.

:: 3. टनल प्रारम्भ करना (Streamlit डिफ़ॉल्ट रूप से 8501 पोर्ट का उपयोग करता है)
ngrok http 8501

pause