"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { AlertTriangle, Copy, Download, Mic, Pause, Play, RotateCcw, Sparkles, Square, Trash2, Upload } from "lucide-react";
import { recordingsApi } from "@/lib/api/integrations";
import type { MeetingRecording, TranscriptionConfig } from "@/types";
import { Button } from "@/components/ui/Button";
import { Badge } from "@/components/ui/Badge";
import { Spinner } from "@/components/ui/Spinner";
import { ConfirmDialog } from "@/components/ui/Modal";
import { useToast } from "@/components/ui/Toast";
import { formatDateTime, formatDuration } from "@/lib/format";
import { cn } from "@/lib/utils";

type RecorderState = "idle" | "requesting" | "recording" | "paused" | "uploading" | "upload_failed";

const MIME_CANDIDATES = ["audio/webm;codecs=opus", "audio/webm", "audio/mp4", "audio/ogg;codecs=opus"];
const CONSENT_NOTICE = "Make sure all participants have been informed and consent to recording where required.";

function pickMimeType(): string | undefined {
  if (typeof MediaRecorder === "undefined") return undefined;
  return MIME_CANDIDATES.find((t) => MediaRecorder.isTypeSupported(t));
}

/**
 * Record a meeting in the browser, upload it, and show its transcript.
 * Audio goes to private storage via the API; transcription runs in the
 * background and this component polls until it finishes.
 */
export function MeetingRecorder({ meetingId, disabled = false }: { meetingId: string; disabled?: boolean }) {
  const toast = useToast();
  const [state, setState] = useState<RecorderState>("idle");
  const [elapsed, setElapsed] = useState(0);
  const [progress, setProgress] = useState(0);
  const [recordings, setRecordings] = useState<MeetingRecording[] | null>(null);
  const [config, setConfig] = useState<TranscriptionConfig | null>(null);
  const [error, setError] = useState<string | null>(null);

  const recorderRef = useRef<MediaRecorder | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const pendingBlobRef = useRef<Blob | null>(null);
  // Elapsed time excluding pauses: accumulated ms + start of the current run.
  const accumulatedRef = useRef(0);
  const runStartRef = useRef<number | null>(null);

  const loadRecordings = useCallback(() => {
    recordingsApi.list(meetingId).then(setRecordings).catch(() => setRecordings([]));
  }, [meetingId]);

  useEffect(() => {
    loadRecordings();
    recordingsApi.config().then(setConfig).catch(() => setConfig(null));
  }, [loadRecordings]);

  // Poll while any recording is still being processed.
  useEffect(() => {
    if (!recordings?.some((r) => r.status === "processing" || r.status === "uploading")) return;
    const t = setTimeout(loadRecordings, 5000);
    return () => clearTimeout(t);
  }, [recordings, loadRecordings]);

  // Live timer.
  useEffect(() => {
    if (state !== "recording") return;
    const t = setInterval(() => {
      const run = runStartRef.current ? Date.now() - runStartRef.current : 0;
      setElapsed((accumulatedRef.current + run) / 1000);
    }, 250);
    return () => clearInterval(t);
  }, [state]);

  // Don't let a tab close silently discard a recording.
  useEffect(() => {
    if (!["recording", "paused", "uploading", "upload_failed"].includes(state)) return;
    const onBeforeUnload = (e: BeforeUnloadEvent) => {
      e.preventDefault();
      e.returnValue = "";
    };
    window.addEventListener("beforeunload", onBeforeUnload);
    return () => window.removeEventListener("beforeunload", onBeforeUnload);
  }, [state]);

  useEffect(() => () => streamRef.current?.getTracks().forEach((t) => t.stop()), []);

  async function start() {
    setError(null);
    if (!navigator.mediaDevices?.getUserMedia || typeof MediaRecorder === "undefined") {
      setError("This browser can't record audio. Try a current version of Chrome, Edge, Firefox or Safari.");
      return;
    }
    setState("requesting");
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true },
      });
      streamRef.current = stream;
      const mimeType = pickMimeType();
      const recorder = new MediaRecorder(stream, { ...(mimeType ? { mimeType } : {}), audioBitsPerSecond: 48000 });
      chunksRef.current = [];
      recorder.ondataavailable = (e) => {
        if (e.data.size > 0) chunksRef.current.push(e.data);
      };
      recorder.onstop = () => {
        stream.getTracks().forEach((t) => t.stop());
        const blob = new Blob(chunksRef.current, { type: recorder.mimeType || mimeType || "audio/webm" });
        pendingBlobRef.current = blob;
        void upload(blob);
      };
      recorderRef.current = recorder;
      accumulatedRef.current = 0;
      runStartRef.current = Date.now();
      setElapsed(0);
      recorder.start(1000);
      setState("recording");
    } catch (err) {
      setState("idle");
      const denied = err instanceof DOMException && (err.name === "NotAllowedError" || err.name === "SecurityError");
      setError(denied ? "Microphone access was blocked. Allow microphone access for this site and try again." : "Couldn't start recording — no microphone found.");
    }
  }

  function pause() {
    const r = recorderRef.current;
    if (!r || r.state !== "recording") return;
    r.pause();
    if (runStartRef.current) accumulatedRef.current += Date.now() - runStartRef.current;
    runStartRef.current = null;
    setElapsed(accumulatedRef.current / 1000);
    setState("paused");
  }

  function resume() {
    const r = recorderRef.current;
    if (!r || r.state !== "paused") return;
    r.resume();
    runStartRef.current = Date.now();
    setState("recording");
  }

  function stop() {
    const r = recorderRef.current;
    if (!r || r.state === "inactive") return;
    if (runStartRef.current) accumulatedRef.current += Date.now() - runStartRef.current;
    runStartRef.current = null;
    setElapsed(accumulatedRef.current / 1000);
    setState("uploading");
    r.stop(); // -> onstop -> upload
  }

  async function upload(blob: Blob) {
    setState("uploading");
    setProgress(0);
    if (config && blob.size > config.max_upload_mb * 1024 * 1024) {
      setState("upload_failed");
      setError(`The recording is larger than the ${config.max_upload_mb} MB upload limit. Download it to keep a copy.`);
      return;
    }
    try {
      const rec = await recordingsApi.upload(meetingId, blob, accumulatedRef.current / 1000, setProgress);
      pendingBlobRef.current = null;
      setRecordings((prev) => [rec, ...(prev ?? [])]);
      setState("idle");
      setElapsed(0);
      toast({ title: "Recording saved", description: "Processing recording...", variant: "success" });
    } catch (err) {
      setState("upload_failed");
      setError(`Upload failed: ${err instanceof Error ? err.message : "unknown error"}. Your recording is still here — retry or download it.`);
    }
  }

  function downloadPending() {
    const blob = pendingBlobRef.current;
    if (!blob) return;
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `meeting-recording.${blob.type.includes("mp4") ? "m4a" : "webm"}`;
    a.click();
    URL.revokeObjectURL(url);
  }

  const active = state === "recording" || state === "paused";

  return (
    <div className="space-y-4">
      <div className="rounded-xl border border-navy-100 bg-white p-4 shadow-card">
        <div className="mb-3 flex items-center justify-between">
          <h2 className="flex items-center gap-2 text-sm font-semibold text-navy-800">
            <Mic className="h-4 w-4 text-teal-500" />
            Meeting Recording
          </h2>
          {config && !config.enabled && <Badge tone="warning">Transcription not configured</Badge>}
        </div>

        {state === "idle" || state === "requesting" ? (
          <>
            <p className="mb-3 flex items-start gap-2 rounded-lg bg-navy-50 px-3 py-2 text-xs text-navy-600">
              <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-warning" />
              {CONSENT_NOTICE}
            </p>
            <Button className="w-full" size="lg" onClick={start} disabled={disabled || state === "requesting"}>
              {state === "requesting" ? <Spinner className="h-4 w-4 text-white" /> : <Mic className="h-4 w-4" />}
              Start Recording
            </Button>
          </>
        ) : active ? (
          <div className="space-y-3">
            <div className="flex items-center justify-center gap-3 py-2">
              <span className={cn("h-3 w-3 rounded-full", state === "recording" ? "animate-pulse bg-danger" : "bg-navy-300")} />
              <span className="text-sm font-medium text-navy-600">{state === "recording" ? "Recording..." : "Paused"}</span>
              <span className="font-mono text-2xl font-semibold tabular-nums text-navy-900">{formatDuration(elapsed)}</span>
            </div>
            <div className="grid grid-cols-2 gap-2">
              {state === "recording" ? (
                <Button variant="secondary" size="lg" onClick={pause}>
                  <Pause className="h-4 w-4" /> Pause
                </Button>
              ) : (
                <Button variant="secondary" size="lg" onClick={resume}>
                  <Play className="h-4 w-4" /> Resume
                </Button>
              )}
              <Button variant="danger" size="lg" onClick={stop}>
                <Square className="h-4 w-4" /> Stop
              </Button>
            </div>
          </div>
        ) : state === "uploading" ? (
          <div className="space-y-2 py-1">
            <div className="flex items-center gap-2 text-sm text-navy-600">
              <Spinner className="h-4 w-4" /> Uploading recording ({formatDuration(elapsed)})... {Math.round(progress * 100)}%
            </div>
            <div className="h-1.5 overflow-hidden rounded-full bg-navy-100">
              <div className="h-full bg-teal-500 transition-all" style={{ width: `${Math.round(progress * 100)}%` }} />
            </div>
          </div>
        ) : (
          <div className="flex flex-wrap gap-2">
            <Button onClick={() => pendingBlobRef.current && upload(pendingBlobRef.current)}>
              <Upload className="h-4 w-4" /> Retry upload
            </Button>
            <Button variant="secondary" onClick={downloadPending}>
              <Download className="h-4 w-4" /> Download audio
            </Button>
          </div>
        )}

        {error && <p className="mt-3 text-sm text-danger">{error}</p>}
      </div>

      {recordings && recordings.length > 0 && (
        <div className="space-y-3">
          {recordings.map((r) => (
            <RecordingCard key={r.id} recording={r} onChanged={loadRecordings} />
          ))}
        </div>
      )}
    </div>
  );
}

function RecordingCard({ recording, onChanged }: { recording: MeetingRecording; onChanged: () => void }) {
  const toast = useToast();
  const [confirmDelete, setConfirmDelete] = useState(false);
  const transcript = recording.transcript;

  async function handleRetry() {
    try {
      await recordingsApi.retry(recording.id);
      onChanged();
    } catch (err) {
      toast({ title: "Couldn't retry", description: err instanceof Error ? err.message : undefined, variant: "error" });
    }
  }

  async function handleDelete() {
    try {
      await recordingsApi.remove(recording.id);
      toast({ title: "Recording deleted", variant: "success" });
      onChanged();
    } catch (err) {
      toast({ title: "Couldn't delete recording", description: err instanceof Error ? err.message : undefined, variant: "error" });
    }
    setConfirmDelete(false);
  }

  async function handleCopy() {
    if (!transcript) return;
    await navigator.clipboard.writeText(
      (transcript.segments ?? []).map((s) => `Speaker ${s.speaker}: ${s.text}`).join("\n\n") || transcript.text
    );
    toast({ title: "Transcript copied", variant: "success" });
  }

  async function handleDownload() {
    try {
      await recordingsApi.downloadTranscript(recording.id);
    } catch (err) {
      toast({ title: "Couldn't download transcript", description: err instanceof Error ? err.message : undefined, variant: "error" });
    }
  }

  return (
    <div className="rounded-xl border border-navy-100 bg-white shadow-card">
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-navy-100 px-4 py-3">
        <div className="min-w-0">
          <p className="text-sm font-semibold text-navy-800">
            {transcript ? "Meeting Transcript" : "Recording"}
          </p>
          <p className="text-xs text-navy-500">
            {formatDateTime(recording.created_at)}
            {recording.created_by_name && ` · ${recording.created_by_name}`}
          </p>
        </div>
        <div className="flex items-center gap-1">
          {recording.status === "completed" && <Badge tone="success">Transcript ready</Badge>}
          {recording.status === "failed" && <Badge tone="danger">Failed</Badge>}
          {recording.can_delete && (
            <Button variant="ghost" size="sm" onClick={() => setConfirmDelete(true)} aria-label="Delete recording" title="Delete recording">
              <Trash2 className="h-3.5 w-3.5" />
            </Button>
          )}
        </div>
      </div>

      <div className="space-y-3 px-4 py-3 text-sm">
        {(recording.status === "processing" || recording.status === "uploading") && (
          <div className="flex items-center gap-2 rounded-lg bg-teal-50 px-3 py-2 text-teal-700">
            <Spinner className="h-4 w-4 text-teal-600" />
            {recording.provider ? "Generating transcript..." : "Processing recording..."}
          </div>
        )}

        {recording.status === "failed" && (
          <div className="space-y-2">
            <p className="flex items-start gap-2 rounded-lg bg-amber-50 px-3 py-2 text-warning">
              <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
              {recording.error || "Transcription failed."}
            </p>
            <Button variant="secondary" size="sm" onClick={handleRetry}>
              <RotateCcw className="h-3.5 w-3.5" /> Retry transcription
            </Button>
          </div>
        )}

        <dl className="grid grid-cols-2 gap-2 text-xs">
          <div>
            <dt className="text-navy-500">Duration</dt>
            <dd className="font-medium tabular-nums text-navy-800">{formatDuration(transcript?.duration_seconds ?? recording.duration_seconds)}</dd>
          </div>
          {transcript && (
            <div>
              <dt className="text-navy-500">Participants</dt>
              <dd className="font-medium text-navy-800">
                {transcript.speaker_count ? `${transcript.speaker_count} speaker${transcript.speaker_count === 1 ? "" : "s"} detected` : "—"}
              </dd>
            </div>
          )}
        </dl>

        {recording.status !== "uploading" && (
          <audio controls preload="none" src={recordingsApi.audioUrl(recording.id)} className="h-9 w-full" />
        )}

        {transcript && (
          <>
            <div className="flex flex-wrap gap-2">
              <Button variant="secondary" size="sm" onClick={handleCopy}>
                <Copy className="h-3.5 w-3.5" /> Copy Transcript
              </Button>
              <Button variant="secondary" size="sm" onClick={handleDownload}>
                <Download className="h-3.5 w-3.5" /> Download Transcript
              </Button>
              <Button variant="ghost" size="sm" disabled title="Coming soon">
                <Sparkles className="h-3.5 w-3.5" /> Generate Meeting Summary
              </Button>
            </div>
            <div className="scrollbar-thin max-h-96 space-y-3 overflow-y-auto rounded-lg border border-navy-50 bg-navy-50/40 p-3">
              {(transcript.segments ?? []).map((s, i) => (
                <div key={i}>
                  <p className="mb-0.5 flex items-center gap-2 text-xs font-semibold">
                    <span className={speakerColor(s.speaker)}>Speaker {s.speaker}</span>
                    <span className="font-normal tabular-nums text-navy-400">{formatDuration(s.start)}</span>
                  </p>
                  <p className="leading-relaxed text-navy-800">{s.text}</p>
                </div>
              ))}
            </div>
          </>
        )}
      </div>

      <ConfirmDialog
        open={confirmDelete}
        title="Delete recording"
        description="This permanently deletes the audio and its transcript. This cannot be undone."
        confirmLabel="Delete"
        danger
        onConfirm={handleDelete}
        onCancel={() => setConfirmDelete(false)}
      />
    </div>
  );
}

const SPEAKER_COLORS = ["text-teal-700", "text-navy-700", "text-warning", "text-success", "text-danger"];
function speakerColor(speaker: string) {
  const n = parseInt(speaker, 10);
  return SPEAKER_COLORS[(Number.isFinite(n) ? n - 1 : 0) % SPEAKER_COLORS.length];
}
