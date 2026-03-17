/**
 * Offline Registration Service
 * Uses Dexie.js (IndexedDB wrapper) to store registrations captured offline.
 * Records expire after 72 hours — enforced both client-side and server-side.
 */

import Dexie, { Table } from "dexie";

export interface OfflineRegistration {
  id?: number;           // Auto-incremented local ID
  offlineId: string;     // UUID generated on capture
  workerData: Record<string, unknown>;
  capturedAt: string;    // ISO timestamp
  deviceFingerprint: string;
  syncStatus: "pending" | "synced" | "expired" | "error";
  syncedWorkerId?: string;
  retryCount: number;
  lastError?: string;
}

class OfflineDatabase extends Dexie {
  registrations!: Table<OfflineRegistration>;

  constructor() {
    super("DWRSOfflineDB");
    this.version(1).stores({
      registrations: "++id, offlineId, syncStatus, capturedAt",
    });
  }
}

const db = new OfflineDatabase();

// Max offline storage age (hours) — must match backend setting
const MAX_AGE_HOURS = 72;

export class OfflineRegistrationService {

  async queue(workerData: Record<string, unknown>): Promise<string> {
    const offlineId = crypto.randomUUID();
    await db.registrations.add({
      offlineId,
      workerData,
      capturedAt: new Date().toISOString(),
      deviceFingerprint: await getDeviceFingerprint(),
      syncStatus: "pending",
      retryCount: 0,
    });
    return offlineId;
  }

  async getPending(): Promise<OfflineRegistration[]> {
    const all = await db.registrations
      .where("syncStatus")
      .equals("pending")
      .toArray();

    // Mark expired records
    const now = Date.now();
    const result: OfflineRegistration[] = [];
    for (const record of all) {
      const ageHours = (now - new Date(record.capturedAt).getTime()) / 3600000;
      if (ageHours > MAX_AGE_HOURS) {
        await db.registrations.update(record.id!, { syncStatus: "expired" });
      } else {
        result.push(record);
      }
    }
    return result;
  }

  async getPendingCount(): Promise<number> {
    return db.registrations.where("syncStatus").equals("pending").count();
  }

  async markSynced(offlineId: string, workerId: string): Promise<void> {
    await db.registrations
      .where("offlineId").equals(offlineId)
      .modify({ syncStatus: "synced", syncedWorkerId: workerId });
  }

  async markError(offlineId: string, error: string): Promise<void> {
    const record = await db.registrations.where("offlineId").equals(offlineId).first();
    if (record) {
      const newCount = (record.retryCount || 0) + 1;
      await db.registrations
        .where("offlineId").equals(offlineId)
        .modify({
          syncStatus: newCount >= 3 ? "error" : "pending",
          retryCount: newCount,
          lastError: error,
        });
    }
  }

  async syncAll(apiUrl: string, token: string): Promise<SyncResult[]> {
    const pending = await this.getPending();
    const results: SyncResult[] = [];

    for (const record of pending) {
      try {
        const response = await fetch(`${apiUrl}/registration/offline-sync`, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "Authorization": `Bearer ${token}`,
          },
          body: JSON.stringify({
            batch_id: crypto.randomUUID(),
            records: [{
              local_id: record.offlineId,
              worker_data: record.workerData,
              captured_at: record.capturedAt,
              device_fingerprint: record.deviceFingerprint,
            }],
          }),
        });

        if (!response.ok) throw new Error(`HTTP ${response.status}`);

        const data = await response.json();
        const result = data[0];

        if (result.status === "synced") {
          await this.markSynced(record.offlineId, result.worker_id);
          results.push({ offlineId: record.offlineId, status: "synced", workerId: result.worker_id });
        } else if (result.status === "expired") {
          await db.registrations.where("offlineId").equals(record.offlineId)
            .modify({ syncStatus: "expired" });
          results.push({ offlineId: record.offlineId, status: "expired", reason: result.reason });
        } else {
          await this.markError(record.offlineId, result.reason || "Rejected by server");
          results.push({ offlineId: record.offlineId, status: "error", reason: result.reason });
        }
      } catch (e) {
        await this.markError(record.offlineId, String(e));
        results.push({ offlineId: record.offlineId, status: "error", reason: String(e) });
      }
    }
    return results;
  }
}

export interface SyncResult {
  offlineId: string;
  status: "synced" | "expired" | "error";
  workerId?: string;
  reason?: string;
}

async function getDeviceFingerprint(): Promise<string> {
  // Lightweight fingerprint using navigator properties
  const components = [
    navigator.userAgent,
    navigator.language,
    screen.width + "x" + screen.height,
    Intl.DateTimeFormat().resolvedOptions().timeZone,
  ].join("|");
  const buf = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(components));
  return Array.from(new Uint8Array(buf)).map(b => b.toString(16).padStart(2, "0")).join("").slice(0, 32);
}

export const offlineRegistrationService = new OfflineRegistrationService();
