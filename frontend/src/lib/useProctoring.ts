import { useEffect, useState } from "react";
import { api } from "../api";

export type CameraState = "off" | "starting" | "on" | "blocked";

/**
 * Browser-side proctoring the candidate consented to: logs focus/clipboard/fullscreen
 * events and uploads a small webcam still every `intervalSeconds`. No face recognition
 * or other biometric processing happens anywhere; the recruiter just sees the images.
 */
export function useProctoring(token: string, active: boolean, intervalSeconds: number) {
  const [camera, setCamera] = useState<CameraState>("off");

  useEffect(() => {
    if (!active) return;
    const send = (kind: string, detail = "") =>
      api.sendEvent(token, kind, detail).catch((err: Error) => {
        console.warn(`Could not record proctoring event "${kind}": ${err.message}`);
      });

    const onVisibility = () => send(document.hidden ? "tab_hidden" : "tab_visible");
    const onBlur = () => send("window_blur");
    const onFullscreen = () => !document.fullscreenElement && send("fullscreen_exit");
    const onCopy = () => send("copy");
    const onPaste = (e: ClipboardEvent) =>
      send("paste", `${e.clipboardData?.getData("text").length ?? 0} characters`);
    document.addEventListener("visibilitychange", onVisibility);
    window.addEventListener("blur", onBlur);
    document.addEventListener("fullscreenchange", onFullscreen);
    document.addEventListener("copy", onCopy);
    document.addEventListener("paste", onPaste);

    let stopped = false;
    let stream: MediaStream | null = null;
    let firstShot: number | undefined;
    let timer: number | undefined;
    const video = document.createElement("video");
    video.muted = true;
    video.playsInline = true;

    const capture = () => {
      const canvas = document.createElement("canvas");
      canvas.width = 320;
      canvas.height = 240;
      canvas.getContext("2d")?.drawImage(video, 0, 0, canvas.width, canvas.height);
      canvas.toBlob(
        (blob) =>
          blob &&
          api.uploadSnapshot(token, blob).catch((err: Error) => {
            console.warn(`Snapshot upload failed: ${err.message}`);
          }),
        "image/jpeg",
        0.7,
      );
    };

    if (intervalSeconds > 0) {
      setCamera("starting");
      const media = navigator.mediaDevices?.getUserMedia({ video: { width: 320, height: 240 } });
      (media ?? Promise.reject(new Error("Camera API unavailable")))
        .then(async (s) => {
          if (stopped) return s.getTracks().forEach((t) => t.stop());
          stream = s;
          video.srcObject = s;
          await video.play();
          if (stopped) return;
          setCamera("on");
          firstShot = window.setTimeout(capture, 1500);
          timer = window.setInterval(capture, intervalSeconds * 1000);
        })
        .catch((err: Error) => {
          setCamera("blocked");
          send("camera_unavailable", err.name || err.message);
        });
    }

    return () => {
      stopped = true;
      window.clearTimeout(firstShot);
      window.clearInterval(timer);
      stream?.getTracks().forEach((t) => t.stop());
      document.removeEventListener("visibilitychange", onVisibility);
      window.removeEventListener("blur", onBlur);
      document.removeEventListener("fullscreenchange", onFullscreen);
      document.removeEventListener("copy", onCopy);
      document.removeEventListener("paste", onPaste);
    };
  }, [token, active, intervalSeconds]);

  return camera;
}
