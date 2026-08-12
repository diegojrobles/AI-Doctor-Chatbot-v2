# 🩺 AI Doctor App  
**GDG Mentorship Project • AI-powered Primary Care Companion**

Mentees: Yui, Dustin, Hana, Diego

A mobile-first healthcare assistant built with **React Native (Expo)** and **FastAPI**, designed to provide:
- At-home care suggestions (non-diagnostic)  
- Clinician-reviewed specialist referrals  
- Clinician-only prescription drafts  
- Safety-first design: JSON-only LLM responses, triage validation, and audit logging  

---

## 🧠 Objective
The goal of the **AI Doctor App** is to empower patients with safe, responsible, AI-guided triage and health suggestions — while supporting clinicians through explainable AI workflows.  
This project is part of the **Google Developer Group (GDG) Mentorship Program**, developed as a capstone for the Fall 2025 cycle.

---

## 🔗 GitHub Repository
**Repo:** [AI-Doctor-App](https://github.com/joebrashear31/AI-Doctor-App)

---

## 🏗 Architecture Overview

| Layer | Tech Stack | Purpose |
|-------|------------|---------|
| **Frontend** | Expo (React Native SDK 52), Expo Router | Patient-facing app with symptom input, triage, and advice chat |
| **Backend** | FastAPI (Python, Dockerized) | Exposes secure API routes and enforces LLM JSON output guardrails |
| **LLM Provider** | OpenRouter (Meta Llama 3.3 70B Instruct) / Ollama local option | Natural language processing and medical context generation |
| **Deployment** | Docker + Azure / AWS / GCP | Cloud hosting and CI/CD ready |
| **Safety** | Red-flag triage, JSON repair, medication filter | Prevents unsafe or incomplete AI outputs |

---

## 🚀 Getting Started

### 1️⃣ Clone the Repository
```bash
git clone https://github.com/diegojrobles/AI-Doctor-Chatbot-v2.git
cd AI-Doctor-Chatbot-v2
```

### 2️⃣ Backend Setup (FastAPI)
```bash
cd server
cp .env.example .env
# Add your API key and configuration to .env
docker compose up --build
```

Verify the backend:
```bash
curl http://localhost:8000/health
# → {"ok": true}
```

### 3️⃣ Frontend Setup (Expo)
```bash
cd ..
npm install
npx expo start
```

Run on:
- **iOS simulator** → press `i`  
- **Android emulator** → press `a`  
- **Physical phone** → scan QR (Expo Go app)  

> For real devices, update the `BASE_URL` in your API file to your LAN IP, e.g. `http://192.168.x.x:8000`

---

## ⚙️ Environment Variables (`server/.env`)
```env
OPENROUTER_API_KEY=or-xxxxxxxxxxxxxxxx
MODEL=meta-llama/llama-3.3-70b-instruct:free
APP_REFERER=http://localhost:8000
APP_TITLE=AI Doctor App
ALLOWED_ORIGINS=*
# Optional for local inference
OLLAMA_URL=http://host.docker.internal:11434
```

---

## 🔌 API Endpoints

| Endpoint | Method | Description |
|-----------|---------|-------------|
| `/health` | GET | Check server status |
| `/triage` | POST | Classifies risk level and red flags |
| `/advice` | POST | Provides safe, at-home advice |
| `/referrals` | POST | Suggests specialist referrals (clinician-only) |
| `/rx_draft` | POST | Drafts prescription options (clinician-only) |

---

## 🧩 Example API Response

### `/advice`
```json
{
  "advice": [
    { "step": "Hydration", "details": "Drink small sips of water throughout the day." }
  ],
  "when_to_seek_care": ["High fever for more than 3 days", "Shortness of breath"],
  "disclaimer": "This is not a diagnosis. Consult a physician if symptoms persist."
}
```

---

## 🧱 Features & Safety

- ✅ **Emergency triage** detection prevents unsafe advice  
- ✅ **LLM JSON repair + retry** to avoid malformed responses  
- ✅ **Medication instruction filters** for patient outputs  
- ✅ **Clinician review layer** for all Rx & referral suggestions  
- ✅ **Dockerized deployment** for fast setup and reproducibility  

---

## 🌱 Possible Enhancements

- ☁️ Host API in the cloud (GCP, AWS, or Azure)  
- 🔐 Add clinician & patient authentication portals  
- 🩺 Integrate EHR/FHIR APIs for verified patient data  
- 📚 Implement RAG-based medical reference retrieval  
- 📊 Add symptom tracking and analytics dashboards  
- 🧾 Enforce HIPAA compliance and data encryption  
- 💻 Switch to **Ollama** for local on-device inference  

---

## 🗓 **Updated Project Timeline (GDG Mentorship – Oct to Nov 2025)**

### **Week 1 (Oct 6 – Oct 12, 2025) – Cloud Backend & API Hosting**
- Deploy the existing FastAPI backend to a cloud provider (Azure App Service, AWS ECS, or Google Cloud Run).  
- Configure environment variables securely in the cloud environment.  
- Verify health check and all `/triage`, `/advice`, `/referrals`, `/rx_draft` routes externally.  
- Update React Native app `BASE_URL` to point to the hosted API.  

---

### **Week 2 (Oct 13 – Oct 19, 2025) – Authentication & Access Control**
- Implement clinician and patient login portals (JWT or Firebase Auth).  
- Create user roles (`patient`, `clinician`) and secure routes accordingly.  
- Add backend middleware to log all API requests by user role and timestamp.  
- Add basic UI for login and account creation in Expo.  

---

### **Week 3 (Oct 20 – Oct 26, 2025) – EHR Integration (FHIR API)**
- Research and integrate public EHR API endpoints (Epic, Cerner, or Google Cloud Healthcare FHIR).  
- Implement endpoints to pull anonymized or mock patient data for testing.  
- Add environment variable toggles to enable or disable EHR sync.  
- Ensure compliance with privacy standards (no PHI stored locally).  

---

### **Week 4 (Oct 27 – Nov 2, 2025) – RAG Medical Knowledge Retrieval**
- Implement Retrieval-Augmented Generation (RAG) pipeline using medical literature (e.g., PubMed, CDC).  
- Host vector database (FAISS, Chroma, or Pinecone).  
- Modify `/advice` endpoint to enrich LLM context with retrieved references.  
- Test factual grounding improvements vs baseline responses.  

---

### **Week 5 (Nov 3 – Nov 9, 2025) – Symptom Tracking & Analytics Dashboard**
- Add frontend charts for tracking symptoms over time (React Native Charts or Recharts).  
- Log user interactions and triage results in Firestore or local DB.  
- Build a clinician dashboard for visualizing condition trends.  
- Integrate optional push notifications or reminders.  

---

### **Week 6 (Nov 10 – Nov 16, 2025) – Security, Compliance & On-Device LLM Support**
- Implement encryption for stored health data and enforce consent flow.  
- Add Terms of Use and Privacy Policy screens with acknowledgment tracking.  
- Explore switching LLM provider from OpenRouter → Ollama for offline inference.  
- Final mobile testing (iOS, Android, physical devices) and demo deployment.  
- Prepare final presentation of project to mentor!  

---

### **🎉 November 15th – GDG DevFest**

---

### **🏁 November 17th – End of Semester**
- Wrap-up and reflect with mentors.  
- Maintain communication with mentors for ongoing feedback and research alignment.  



## 🧑‍💻 Contributors
**Project Lead:** [William J. Brashear](https://github.com/joebrashear31)  
**Mentorship Program:** Google Developer Group (GDG) at the University of South Florida
**Students** Diego, Yui, Hana, Dustin

---

## ⚠️ Disclaimer
This application is a **research and educational tool**, not a medical device.  
It does **not** diagnose, treat, or replace clinical judgment. Always consult a licensed physician before acting on medical information.

---

## 🏁 License
MIT License © 2025 William J. Brashear  
Open-source contributions welcome!
