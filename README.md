---
title: Burn Assessment
emoji: 🔥
colorFrom: red
colorTo: orange
sdk: gradio
sdk_version: 6.14.0
app_file: app.py
pinned: false
---

# 🔥 Burn Wound Assessment System (Web)

Web-deployable AI-powered burn injury assessment.
- 📸 Upload burn photo → AI vision analysis (Gemini)
- 📊 TBSA estimation via Lund-Browder chart (age-adjusted)
- 💧 Parkland fluid resuscitation calculation
- 📚 Clinical explanation via RAG (ChromaDB knowledge base + Gemini)

This is a single-file Gradio app deployed on Hugging Face Spaces.

---

## 🚀 Run Locally

### 1. Prerequisites
- Python 3.10 or newer
- Gemini API key (free): https://aistudio.google.com/apikey

### 2. Setup
```bash
git clone <this-repo-url>
cd burn_assessment_web

python3 -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

pip install -r requirements.txt
```

### 3. Configure API key
```bash
cp .env.example .env
# Edit .env, replace `your_key_here` with your actual Gemini key
```

### 4. Run
```bash
python app.py
```

Open http://localhost:7860

First run downloads the embedding model (~90 MB) and builds the RAG index (~15 sec total).

---

## ☁️ Deploy to Hugging Face Spaces

### One-time setup

1. Create account at https://huggingface.co (free)
2. **Get a write-enabled access token:** Settings → Access Tokens → New token → Role: Write → save the value
3. Create new Space:
   - https://huggingface.co/new-space
   - Owner: your username
   - Space name: `burn-assessment` (or any slug)
   - License: MIT
   - SDK: **Gradio**
   - Hardware: **CPU basic (free)**
4. Add the API key as a Secret:
   - In the Space → Settings → Variables and secrets → New secret
   - Name: `GEMINI_API_KEY`
   - Value: your Gemini API key from aistudio.google.com

### Deploy

The Space provides a Git URL. Add it as a remote and push:

```bash
cd burn_assessment_web

# Add the HF Space as a remote (use your username and space name)
git remote add hf https://huggingface.co/spaces/YOUR_USERNAME/burn-assessment

# Push (you'll be prompted for username and the access token from step 2)
git push hf master:main
```

HF Spaces will install dependencies and start the app (2–5 minutes).
When done, the app is live at:
```
https://YOUR_USERNAME-burn-assessment.hf.space
```

### Updating the deployment

After making changes:
```bash
git add .
git commit -m "your change"
git push hf master:main
```

The Space auto-rebuilds on each push.

---

## 📁 Project Structure

```
burn_assessment_web/
├── app.py                 # Gradio UI + Gemini vision + analyze() orchestrator
├── calculator.py          # Lund-Browder chart + Parkland formula (pure logic)
├── rag_engine.py          # ChromaDB retrieval + Gemini explanation
├── knowledge_base/        # 7 medical reference .txt files
├── tests/                 # pytest unit tests
├── requirements.txt
├── .env.example
└── README.md (this file)
```

---

## 🛠️ Tech Stack

- **UI:** Gradio 6.x
- **AI Vision + Text:** Google Gemini API (free tier)
- **Vector store:** ChromaDB (persistent)
- **Embeddings:** sentence-transformers/all-MiniLM-L6-v2
- **Hosting:** Hugging Face Spaces (free CPU)

---

## ⚠️ Medical Disclaimer

This tool is a **clinical aid**, not a substitute for professional medical judgment.
- AI TBSA estimates are approximations and must be clinically verified.
- Always confirm with a physical Lund-Browder chart.
- Parkland formula gives an initial estimate — adjust based on actual urine output.
- Final clinical decisions belong to the responsible clinician.

---

## 🧪 Run tests

```bash
source venv/bin/activate
pytest tests/ -v
```

Smoke tests that hit Gemini are skipped automatically if `GEMINI_API_KEY` is unset or still the placeholder.
# MedAssistant
