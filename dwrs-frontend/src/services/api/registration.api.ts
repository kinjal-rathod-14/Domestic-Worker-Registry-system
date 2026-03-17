/**
 * Registration API Service
 * Wraps all registration-related API calls.
 * Falls back to offline queue when network is unavailable.
 */

import { offlineRegistrationService } from "../offline/indexeddb.service";

const BASE_URL = import.meta.env.VITE_API_REGISTRATION_URL ?? "http://localhost:8002";

export interface WorkerRegistrationPayload {
  full_name: string;
  aadhaar_number: string;
  date_of_birth: string;
  gender: string;
  photo_base64: string;
  mobile_number?: string;
  alternate_contact?: string;
  address: {
    house?: string;
    street?: string;
    village?: string;
    district: string;
    state: string;
    pincode: string;
  };
  registration_mode: "self" | "assisted_officer" | "assisted_employer" | "offline";
  assisted_by_officer_id?: string;
  employer_id?: string;
  geo_location: {
    lat: number;
    lng: number;
    accuracy_meters: number;
    timestamp?: string;
  };
  consent_recorded: boolean;
  consent_witness?: string;
}

export interface RegistrationResponse {
  worker_id: string;
  registration_number: string;
  status: string;
  risk_level: "low" | "medium" | "high";
  requires_secondary_verification: boolean;
  estimated_approval_hours: number;
}

export interface OfflineQueueResponse {
  offlineId: string;
  status: "queued";
  message: string;
}

class RegistrationApiService {

  async register(
    payload: WorkerRegistrationPayload,
    token: string
  ): Promise<RegistrationResponse | OfflineQueueResponse> {

    // Check connectivity — queue offline if no network
    if (!navigator.onLine) {
      const offlineId = await offlineRegistrationService.queue(payload as Record<string, unknown>);
      return {
        offlineId,
        status: "queued",
        message: "Registration saved offline. Will sync when connectivity is restored.",
      };
    }

    const response = await fetch(`${BASE_URL}/registration/worker`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${token}`,
      },
      body: JSON.stringify(payload),
    });

    if (!response.ok) {
      const error = await response.json().catch(() => ({ detail: "Unknown error" }));
      throw new ApiError(response.status, error.detail ?? "Registration failed");
    }

    return response.json();
  }

  async getWorker(workerId: string, token: string) {
    const response = await fetch(`${BASE_URL}/registration/worker/${workerId}`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    if (!response.ok) throw new ApiError(response.status, "Worker not found");
    return response.json();
  }

  async syncOfflineQueue(token: string) {
    return offlineRegistrationService.syncAll(BASE_URL, token);
  }

  async getPendingOfflineCount(): Promise<number> {
    return offlineRegistrationService.getPendingCount();
  }
}

export class ApiError extends Error {
  constructor(public statusCode: number, message: string) {
    super(message);
    this.name = "ApiError";
  }
}

export const registrationApi = new RegistrationApiService();
