import { useCallback, useEffect, useRef, useState } from "react";
import { useParams } from "react-router-dom";
import { ApiError, api } from "../api";
import { AnswerInput } from "../components/AnswerInput";
import { ErrorBox, Loading } from "../components/Status";
import { TYPE_LABELS, formatClock } from "../lib/format";
import { useLoad } from "../lib/useLoad";
import { type CameraState, useProctoring } from "../lib/useProctoring";
import type { TakeInfo, TestPaper } from "../types";

const CAMERA_TEXT: Record<CameraState, string> = {
  off: "Camera off",
  starting: "Waiting for camera permission…",
  on: "Camera on",
  blocked: "Camera blocked",
};

const CLOSED: Record<string, string> = {
  submitted: "This test has already been submitted. Thank you!",
  graded: "This test has already been submitted. Thank you!",
  expired: "This invite link has expired. Please contact the recruiter.",
  timed_out: "The time for this test has run out.",
};

/** Seconds left, counted down locally from the server's figure (immune to clock skew). */
function useCountdown(seconds: number | null): number | null {
  const [left, setLeft] = useState(seconds);
  useEffect(() => {
    if (seconds === null) return;
    const end = Date.now() + seconds * 1000;
    setLeft(seconds);
    const timer = window.setInterval(() => setLeft(Math.max(0, Math.round((end - Date.now()) / 1000))), 1000);
    return () => window.clearInterval(timer);
  }, [seconds]);
  return left;
}

/** Retry network errors and 429/5xx a few times (the server allows a short grace period). */
async function submitWithRetry(send: () => Promise<unknown>): Promise<void> {
  const delays = [2000, 5000, 10000];
  for (let attempt = 0; ; attempt++) {
    try {
      await send();
      return;
    } catch (err) {
      const permanent = err instanceof ApiError && err.status < 500 && err.status !== 429;
      if (permanent || attempt >= delays.length) throw err;
      await new Promise((resolve) => window.setTimeout(resolve, delays[attempt]));
    }
  }
}

function loadDraft(token: string): Record<number, string> {
  try {
    return JSON.parse(sessionStorage.getItem(`draft:${token}`) ?? "{}");
  } catch {
    return {}; // a corrupt draft is not worth failing the test over
  }
}

function Consent({ info, busy, onStart }: { info: TakeInfo; busy: boolean; onStart: () => void }) {
  const [agreed, setAgreed] = useState(false);
  const interval = info.snapshot_interval_seconds;
  return (
    <section className="card narrow-page">
      <h1>{info.assessment_title}</h1>
      <p>
        Hi {info.candidate_name}. This test has {info.question_count} questions and a {info.duration_minutes}
        -minute time limit. The timer starts when you click Start and keeps running if you close the page.
      </p>
      <h2>Proctoring and your privacy</h2>
      <ul>
        {interval > 0 && (
          <li>
            Your webcam takes a small still photo every {interval} seconds. Only the recruiter can view them.
          </li>
        )}
        <li>We record when you switch tabs or windows, leave full screen, or copy and paste.</li>
        <li>
          No face recognition or biometric analysis is used. A person reviews these signals; nothing is
          decided automatically.
        </li>
        <li>The test opens in full screen. Please stay on this page until you submit.</li>
      </ul>
      <label className="check">
        <input type="checkbox" checked={agreed} onChange={(e) => setAgreed(e.target.checked)} />I understand
        and agree to these proctoring measures.
      </label>
      <div className="row">
        <button type="button" disabled={!agreed || busy} onClick={onStart}>
          {busy ? "Starting…" : info.status === "in_progress" ? "Resume test" : "Start test"}
        </button>
      </div>
      <p className="muted small">If you do not agree, close this page and contact the recruiter.</p>
    </section>
  );
}

export function TakeTestPage() {
  const token = useParams().token ?? "";
  const info = useLoad(() => api.takeInfo(token), [token]);
  const [paper, setPaper] = useState<TestPaper | null>(null);
  const [answers, setAnswers] = useState<Record<number, string>>(() => loadDraft(token));
  const [done, setDone] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const autoSubmitted = useRef(false);
  const testing = paper !== null && !done;
  const camera = useProctoring(token, testing, paper?.snapshot_interval_seconds ?? 0);
  const remaining = useCountdown(paper?.remaining_seconds ?? null);

  useEffect(() => sessionStorage.setItem(`draft:${token}`, JSON.stringify(answers)), [answers, token]);
  useEffect(() => {
    if (done && document.fullscreenElement) void document.exitFullscreen();
  }, [done]);

  const start = async () => {
    setBusy(true);
    setError(null);
    try {
      const root = document.documentElement;
      if (root.requestFullscreen) {
        await root
          .requestFullscreen()
          .catch((err: Error) => console.warn(`Full screen refused: ${err.message}`));
      }
      setPaper(await api.start(token));
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const submit = useCallback(async () => {
    if (!paper) return;
    setBusy(true);
    setError(null);
    try {
      const body = paper.questions.map((q) => ({ question_id: q.id, response: answers[q.id] ?? "" }));
      await submitWithRetry(() => api.submit(token, body));
      sessionStorage.removeItem(`draft:${token}`);
      setDone(true);
    } catch (err) {
      setError((err as Error).message);
      setBusy(false);
    }
  }, [paper, answers, token]);

  useEffect(() => {
    if (testing && remaining === 0 && !autoSubmitted.current) {
      autoSubmitted.current = true;
      void submit();
    }
  }, [testing, remaining, submit]);

  if (info.loading && !info.data) return <Loading />;
  if (info.error) return <ErrorBox message={info.error} onRetry={info.reload} />;
  if (!info.data) return null;
  if (done || CLOSED[info.data.status]) {
    return (
      <section className="card narrow-page">
        <h1>{done ? "Answers submitted" : info.data.assessment_title}</h1>
        <p>
          {done
            ? `Thank you, ${info.data.candidate_name}. You can close this page now.`
            : CLOSED[info.data.status]}
        </p>
      </section>
    );
  }
  if (!paper) {
    return (
      <>
        <Consent info={info.data} busy={busy} onStart={start} />
        {error && <ErrorBox message={error} />}
      </>
    );
  }

  const unanswered = paper.questions.filter((q) => !(answers[q.id] ?? "").trim()).length;
  const secondsLeft = remaining ?? 0;
  return (
    <>
      <div className="test-bar">
        <strong>{info.data.assessment_title}</strong>
        <span className={`camera camera-${camera}`}>{CAMERA_TEXT[camera]}</span>
        <span role="timer" aria-label="Time left" className={secondsLeft < 60 ? "timer urgent" : "timer"}>
          {formatClock(secondsLeft)}
        </span>
      </div>
      <p className="visually-hidden" aria-live="polite">
        {secondsLeft <= 60
          ? "Less than one minute left."
          : secondsLeft <= 300
            ? "Less than five minutes left."
            : ""}
      </p>
      <form
        className="stack"
        onSubmit={(e) => {
          e.preventDefault();
          void submit();
        }}
      >
        {paper.questions.map((q, i) => (
          <section key={q.id} className="card question" aria-labelledby={`q-${q.id}`}>
            <div className="question-head">
              <span className="pill">{TYPE_LABELS[q.type]}</span>
              <span className="muted">{q.points} pt</span>
            </div>
            <p id={`q-${q.id}`} className="prompt">
              {i + 1}. {q.prompt}
            </p>
            <AnswerInput
              question={q}
              name={`q-${q.id}`}
              value={answers[q.id] ?? ""}
              onChange={(v) => setAnswers({ ...answers, [q.id]: v })}
            />
          </section>
        ))}
        {error && <ErrorBox message={error} />}
        <div className="publish-bar">
          <p className="muted">
            {unanswered ? `${unanswered} question(s) unanswered.` : "All questions answered."}
          </p>
          <button type="submit" disabled={busy}>
            {busy ? "Submitting…" : "Submit answers"}
          </button>
        </div>
      </form>
    </>
  );
}
