# 1. पहले ग्लोबल स्तर पर uv इंस्टॉल करें
pip install uv

# 2. Python 3.14 का वर्चुअल एनवायरनमेंट बनाएँ
uv venv --python 3.14

# 3. वर्चुअल एनवायरनमेंट को सक्रिय (Activate) करें
source .venv/bin/activate

# 4. अपनी requirements.txt फ़ाइल से सारे पैकेजेस एक बार में इंस्टॉल करें
uv pip install -r requirements.txt