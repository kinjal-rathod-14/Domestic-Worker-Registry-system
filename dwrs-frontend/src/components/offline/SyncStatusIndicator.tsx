/**
 * SyncStatusIndicator — shows offline queue status in the app header.
 * Displays pending count and triggers sync when clicked.
 */

import React, { useEffect, useState } from "react";
import { offlineRegistrationService } from "../../services/offline/indexeddb.service";
import { registrationApi } from "../../services/api/registration.api";
import { useAppSelector } from "../../app/store";

export const SyncStatusIndicator: React.FC = () => {
  const { token } = useAppSelector((state) => state.auth);
  const [pendingCount, setPendingCount] = useState(0);
  const [isSyncing, setIsSyncing] = useState(false);
  const [isOnline, setIsOnline] = useState(navigator.onLine);

  useEffect(() => {
    const updatePending = async () => {
      const count = await offlineRegistrationService.getPendingCount();
      setPendingCount(count);
    };
    updatePending();
    const interval = setInterval(updatePending, 30_000);

    const handleOnline = () => setIsOnline(true);
    const handleOffline = () => setIsOnline(false);
    window.addEventListener("online", handleOnline);
    window.addEventListener("offline", handleOffline);

    return () => {
      clearInterval(interval);
      window.removeEventListener("online", handleOnline);
      window.removeEventListener("offline", handleOffline);
    };
  }, []);

  // Auto-sync when connectivity returns
  useEffect(() => {
    if (isOnline && pendingCount > 0 && token) {
      handleSync();
    }
  }, [isOnline]);

  const handleSync = async () => {
    if (!token || isSyncing) return;
    setIsSyncing(true);
    try {
      await registrationApi.syncOfflineQueue(token);
      const count = await offlineRegistrationService.getPendingCount();
      setPendingCount(count);
    } finally {
      setIsSyncing(false);
    }
  };

  if (!isOnline) {
    return (
      <div className="flex items-center gap-1.5 px-3 py-1 bg-orange-50 border border-orange-200 rounded-full text-orange-700 text-xs font-medium">
        <span className="w-2 h-2 rounded-full bg-orange-500" />
        Offline
        {pendingCount > 0 && (
          <span className="ml-1 bg-orange-200 px-1.5 py-0.5 rounded-full text-orange-900">
            {pendingCount} pending
          </span>
        )}
      </div>
    );
  }

  if (pendingCount === 0) {
    return (
      <div className="flex items-center gap-1.5 px-3 py-1 text-green-600 text-xs">
        <span className="w-2 h-2 rounded-full bg-green-500" />
        Online
      </div>
    );
  }

  return (
    <button
      onClick={handleSync}
      disabled={isSyncing}
      className="flex items-center gap-1.5 px-3 py-1 bg-blue-50 border border-blue-200 rounded-full text-blue-700 text-xs font-medium hover:bg-blue-100 transition-colors disabled:opacity-60"
      title={`${pendingCount} offline registration(s) pending sync`}
    >
      {isSyncing ? (
        <span className="w-2 h-2 rounded-full border border-blue-600 border-t-transparent animate-spin" />
      ) : (
        <span className="w-2 h-2 rounded-full bg-blue-500" />
      )}
      {isSyncing ? "Syncing..." : `Sync ${pendingCount}`}
    </button>
  );
};

export default SyncStatusIndicator;
