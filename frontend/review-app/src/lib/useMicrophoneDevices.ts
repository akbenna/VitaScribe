"use client";

import { useState, useEffect, useCallback } from "react";

export interface MicrophoneDevice {
  deviceId: string;
  label: string;
}

/**
 * Hook die beschikbare microfoons ophaalt via navigator.mediaDevices.enumerateDevices().
 * Vraagt eenmalig toestemming als labels nog niet zichtbaar zijn.
 * Luistert naar devicechange events zodat nieuwe apparaten automatisch verschijnen.
 */
export function useMicrophoneDevices() {
  const [devices, setDevices] = useState<MicrophoneDevice[]>([]);
  const [selectedDeviceId, setSelectedDeviceId] = useState<string>("");
  const [loading, setLoading] = useState(true);

  const enumerate = useCallback(async () => {
    try {
      let deviceList = await navigator.mediaDevices.enumerateDevices();
      let audioInputs = deviceList.filter((d) => d.kind === "audioinput");

      // Als labels leeg zijn heeft de browser nog geen toestemming gegeven.
      // Vraag kort toegang zodat labels zichtbaar worden.
      if (audioInputs.length > 0 && !audioInputs[0].label) {
        const tempStream = await navigator.mediaDevices.getUserMedia({
          audio: true,
        });
        tempStream.getTracks().forEach((t) => t.stop());
        deviceList = await navigator.mediaDevices.enumerateDevices();
        audioInputs = deviceList.filter((d) => d.kind === "audioinput");
      }

      const mapped: MicrophoneDevice[] = audioInputs.map((d, i) => ({
        deviceId: d.deviceId,
        label: d.label || `Microfoon ${i + 1}`,
      }));

      setDevices(mapped);

      // Herstel eerder gekozen apparaat uit localStorage
      const savedId = localStorage.getItem("sv_selected_mic");
      if (savedId && mapped.some((d) => d.deviceId === savedId)) {
        setSelectedDeviceId(savedId);
      }
    } catch {
      // Geen toestemming of geen apparaten - laat lijst leeg
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    enumerate();
    navigator.mediaDevices.addEventListener("devicechange", enumerate);
    return () => {
      navigator.mediaDevices.removeEventListener("devicechange", enumerate);
    };
  }, [enumerate]);

  const selectDevice = useCallback((deviceId: string) => {
    setSelectedDeviceId(deviceId);
    if (deviceId) {
      localStorage.setItem("sv_selected_mic", deviceId);
    } else {
      localStorage.removeItem("sv_selected_mic");
    }
  }, []);

  return { devices, selectedDeviceId, selectDevice, loading, refresh: enumerate };
}
