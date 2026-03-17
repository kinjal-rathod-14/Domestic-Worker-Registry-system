# DWRS — Domestic Worker Registration & Verification System

Welcome to the **Domestic Worker Registration & Verification System (DWRS)**. This project provides a complete, modern, full-stack solution for registering, verifying, and monitoring domestic workers to ensure safety, trust, and transparency.

## 🚀 Project Overview

The DWRS system is composed of two main parts:
1. **Frontend (`dwrs-frontend`)**: A modern React-based Progressive Web App (PWA) built with Vite, TypeScript, Tailwind CSS, and Redux Toolkit. It features offline-first capabilities, localized caching via Dexie (IndexedDB), and responsive UI layouts.
2. **Backend (`dwrs-backend`)**: A robust, microservices-based Python FastAPI backend. The infrastructure has been adapted to run completely locally without Docker using **SQLite** as the database and **in-memory caching** to replace Redis.

### Architectural Features
- **5 Microservices**: Auth, Registration, Verification, Risk Scoring, Audit.
- **Offline-First PWA**: Can queue registrations and sync when back online (72h sync window).
- **Explainable Risk Scoring**: Rules-based combined with anomaly detection.
- **Microservices Event Bus**: Mocked locally to support Kafka-like decoupled architecture.

---

## 🛠️ Prerequisites

To run this project on your machine, you need:
- **Python 3.10+**
- **Node.js 18+** & npm
- Git (optional, for version control)

---

## 💻 Running the Project Locally (No Docker Required)

We've specifically configured this repository to easily boot up on Windows/Mac/Linux directly using your local hardware—no Docker required!

### 1. Start the Backend Microservices

First, we need to install the dependencies and run the development runner that starts all 5 microservices simultaneously.

```bash
# Navigate to the backend directory
cd dwrs-backend

# Create a virtual environment and activate it
python -m venv venv
# On Windows:
.\venv\Scripts\activate
# On Mac/Linux:
# source venv/bin/activate

# Install required dependencies
pip install -r requirements.txt

# Create your .env file
cp .env.example .env

# Run the backend services
python run_dev.py
```

The backend services will now be running and accessible via their Swagger documentation endpoints:
- Auth: `http://localhost:8001/docs`
- Registration: `http://localhost:8002/docs`
- Verification: `http://localhost:8003/docs`
- Risk Scoring: `http://localhost:8004/docs`
- Audit: `http://localhost:8005/docs`

### 2. Start the Frontend Application

In a **new terminal tab/window**, start the React frontend.

```bash
# Navigate to the frontend directory
cd dwrs-frontend

# Install node dependencies
npm install

# Start the Vite development server
npm run dev
```

The frontend application will now be running at: **`http://localhost:3001`** (or `3000`).

---

## 🌍 Exposing Your Local Server to the Internet

If you need to share your locally running DWRS portal with someone else, you can quickly expose it using Cloudflare's tunneling service.

1. Ensure your frontend is configured to allow the tunnel host (handled in `vite.config.ts` via `server.allowedHosts`).
2. Download and run Cloudflare Tunnel:

```powershell
# On Windows PowerShell
wget "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe" -OutFile "cloudflared.exe"

# Start the tunnel pointing to your frontend
.\cloudflared.exe tunnel --url http://localhost:3001
```

Look for the `trycloudflare.com` URL in the output logs. You can share this secure URL with anyone!

---

## 🏗️ Project Structure

```text
DWRS_Complete_System/
├── dwrs-backend/                # FastAPI Microservices Backend
│   ├── run_dev.py               # Local microservices runner
│   ├── shared/                  # DB, Utils, Shared Event Logic
│   └── services/                # Microservices (auth, audit, risk, etc.)
│
├── dwrs-frontend/               # React + Vite Frontend
│   ├── src/
│   │   ├── components/          # Reusable UI elements
│   │   ├── pages/               # Main application views
│   │   ├── store/               # Redux state management
│   │   └── services/            # API and offline DB integration
│   ├── package.json
│   └── vite.config.ts
│
└── README.md                    # Project Documentation
```

## 📜 License
This proprietary system is developed internally for domestic worker registration and trusted employer-employee matchmaking. All rights reserved.
