# DWRS Frontend — React PWA

Domestic Worker Registration & Verification System — Frontend Application.
Built as a Progressive Web App (PWA) with offline-first capability.

---

## Tech Stack

| Layer          | Technology                                 |
|----------------|--------------------------------------------|
| Framework      | React 18 + TypeScript                      |
| State          | Redux Toolkit + RTK Query                  |
| Routing        | React Router v6                            |
| Styling        | Tailwind CSS                               |
| Offline        | Service Worker + IndexedDB (Dexie.js)      |
| Forms          | React Hook Form + Zod validation           |
| Camera/Biometric | WebRTC (getUserMedia)                   |
| Maps           | Leaflet.js                                 |
| Charts         | Recharts                                   |
| Build          | Vite                                       |

---

## Structure

```
src/
├── app/
│   ├── store.ts                   # Redux store
│   ├── router.tsx                 # Route definitions + guards
│   └── offline-sync.ts            # Service worker sync queue
├── pages/
│   ├── Auth/
│   │   ├── Login.tsx              # Username + password + TOTP
│   │   └── MFAChallenge.tsx       # TOTP entry for officers
│   ├── Registration/
│   │   ├── SelfRegistration.tsx   # Worker self-register
│   │   ├── AssistedRegistration.tsx  # Officer-assisted flow
│   │   ├── OfflineCapture.tsx     # No-connectivity mode
│   │   └── RegistrationSuccess.tsx
│   ├── Dashboard/
│   │   ├── WorkerDashboard.tsx    # Own status + certificate
│   │   ├── OfficerDashboard.tsx   # Today's work + alerts
│   │   ├── SupervisorDashboard.tsx # District + risk queue
│   │   └── AdminDashboard.tsx     # System analytics
│   ├── Verification/
│   │   ├── VerificationPanel.tsx  # Officer verification UI
│   │   ├── FaceCaptureStep.tsx    # WebRTC + liveness
│   │   └── GeoValidationStep.tsx
│   └── Audit/
│       ├── AuditLog.tsx           # Immutable log viewer
│       └── OfficerActivityMap.tsx  # Geo heatmap
├── components/
│   ├── shared/
│   │   ├── ProtectedRoute.tsx     # RBAC route guard
│   │   ├── RiskBadge.tsx          # Low/Medium/High badge
│   │   ├── AuditTrail.tsx         # Inline audit display
│   │   └── SyncStatusBar.tsx      # Offline sync indicator
│   ├── forms/
│   │   ├── BiometricCapture.tsx   # Face photo capture
│   │   ├── AadhaarInput.tsx       # Masked input, format check
│   │   └── GeoCapture.tsx         # GPS capture + accuracy
│   └── offline/
│       ├── SyncStatusIndicator.tsx
│       └── OfflineQueue.tsx
└── services/
    ├── api/
    │   ├── auth.api.ts
    │   ├── registration.api.ts
    │   └── verification.api.ts
    └── offline/
        └── indexeddb.service.ts   # Dexie.js offline storage
```

---

## Quick Start

```bash
npm install
cp .env.example .env.local
npm run dev
```

---

## Environment Variables

```
VITE_API_AUTH_URL=http://localhost:8001
VITE_API_REGISTRATION_URL=http://localhost:8002
VITE_API_VERIFICATION_URL=http://localhost:8003
VITE_API_AUDIT_URL=http://localhost:8005
VITE_OFFLINE_SYNC_MAX_AGE_HOURS=72
```

---

## Key Design Patterns

### 1. Role-based routing

Every route is wrapped with `<ProtectedRoute allowedRoles={[...]} />`.
Unauthorized users are redirected — never shown a 403 error page.

### 2. Offline-first registration

When the device is offline:
- Form data is saved to IndexedDB via `OfflineRegistrationService`
- A `SyncStatusBar` shows pending count
- On reconnection, `SyncManager.syncAll()` runs automatically
- Records older than 72h are marked expired and cannot be synced

### 3. Face capture (WebRTC)

`BiometricCapture.tsx` uses `getUserMedia` to access device camera.
Captures a JPEG frame, runs basic quality checks (resolution, brightness),
then encodes to base64 for the API. Liveness challenge is handled by
the AWS Rekognition Face Liveness SDK embedded in `FaceCaptureStep.tsx`.

### 4. GPS capture

`GeoCapture.tsx` calls `navigator.geolocation.getCurrentPosition` with
`enableHighAccuracy: true`. Displays accuracy in meters to the officer.
Registrations are blocked if accuracy > 200m (configurable).

---

## Build for Production

```bash
npm run build
# Output: dist/ (upload to S3 + CloudFront)
```

---

## PWA Offline Mode

The service worker (`sw.ts`) caches:
- App shell (HTML, CSS, JS)
- Static assets

Does NOT cache:
- API responses (always fresh data required)
- Photos (too large, stored in IndexedDB separately)
