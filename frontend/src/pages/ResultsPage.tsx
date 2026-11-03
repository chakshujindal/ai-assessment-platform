import { type FormEvent, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api } from "../api";
import { Badge, ErrorBox, Loading } from "../components/Status";
import { EVENT_LABELS, TYPE_LABELS, formatClock, formatDate, formatScore } from "../lib/format";
import { useLoad } from "../lib/useLoad";
import type { IntegritySummary, Result, ResultAnswer } from "../types";

const MAX_POLLS = 30; // ~1 minute of polling while background grading runs

function SnapshotImage({ inviteId, snapshot }: { inviteId: number; snapshot: Result["snapshots"][number] }) {
  const [src, setSrc] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);
  const time = new Date(snapshot.taken_at).toLocaleTimeString();

  useEffect(() => {
    let url = "";
    let cancelled = false;
    api.snapshotBlob(inviteId, snapshot.id).then(
      (blob) => {
        if (cancelled) return;
        url = URL.createObjectURL(blob);
        setSrc(url);
      },
      () => setFailed(true),
    );
    return () => {
      cancelled = true;
      if (url) URL.revokeObjectURL(url);
    };
  }, [inviteId, snapshot.id]);

  return (
    <figure className="snapshot">
      {src ? (
        <img src={src} alt={`Webcam snapshot at ${time}`} width={160} height={120} />
      ) : (
        <div className="snapshot-placeholder">{failed ? "Unavailable" : "Loading…"}</div>
      )}
      <figcaption>{time}</figcaption>
    </figure>
  );
}

function IntegrityPanel({ summary, result }: { summary: IntegritySummary; result: Result }) {
  return (
    <section className="card">
      <div className="title-row">
        <h2>Integrity summary</h2>
        <span className={`badge risk-${summary.risk}`}>{summary.risk} risk</span>
      </div>
      <p className="muted small">
        Rule-based signals from the candidate's browser to support your review, not proof of misconduct. No
        face recognition or biometric analysis is used.
      </p>
      {summary.flags.length === 0 ? (
        <p>No flags raised.</p>
      ) : (
        <ul className="flags">
          {summary.flags.map((flag) => (
            <li key={flag.message} className={`flag flag-${flag.level}`}>
              {flag.message}
            </li>
          ))}
        </ul>
      )}
      <dl className="counts">
        {Object.entries(summary.counts).map(([kind, count]) => (
          <div key={kind}>
            <dt>{EVENT_LABELS[kind] ?? kind}</dt>
            <dd>{count}</dd>
          </div>
        ))}
        <div>
          <dt>Time away</dt>
          <dd>{formatClock(summary.time_away_seconds)}</dd>
        </div>
        <div>
          <dt>Webcam snapshots</dt>
          <dd>
            {summary.snapshots_received} / ~{summary.snapshots_expected}
          </dd>
        </div>
      </dl>
      <details>
        <summary>Timeline ({summary.timeline.length} events)</summary>
        <ol className="timeline">
          {summary.timeline.map((event, i) => (
            <li key={i}>
              <span className="mono">+{formatClock(event.offset_seconds)}</span>{" "}
              {EVENT_LABELS[event.kind] ?? event.kind}
              {event.detail && <span className="muted"> ({event.detail})</span>}
            </li>
          ))}
        </ol>
      </details>
      {result.snapshots.length > 0 && (
        <>
          <h3>Webcam snapshots</h3>
          <div className="snapshots">
            {result.snapshots.map((s) => (
              <SnapshotImage key={s.id} inviteId={result.invite.id} snapshot={s} />
            ))}
          </div>
        </>
      )}
    </section>
  );
}

function gradingNote(answer: ResultAnswer): string {
  const base =
    answer.graded_by === "llm"
      ? `AI score ${answer.ai_score} · model ${answer.model_name} · prompt ${answer.prompt_version}`
      : answer.graded_by === "auto"
        ? "Scored automatically"
        : "Not graded yet";
  return answer.override_score === null ? base : `${base} · overridden by recruiter`;
}

function AnswerReview({
  answer,
  index,
  onUpdated,
}: {
  answer: ResultAnswer;
  index: number;
  onUpdated: (a: ResultAnswer) => void;
}) {
  const q = answer.question;
  const [score, setScore] = useState(answer.final_score === null ? "" : String(answer.final_score));
  const [note, setNote] = useState(answer.override_note ?? "");
  const [status, setStatus] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const unanswered = answer.response.trim() === "";
  const response = q.type === "mcq" && !unanswered ? q.options[Number(answer.response)] : answer.response;

  const save = async (event: FormEvent) => {
    event.preventDefault();
    setError(null);
    try {
      const updated = await api.overrideScore(answer.id, Number(score), note);
      onUpdated({ ...answer, ...updated });
      setStatus("Override saved.");
    } catch (err) {
      setError((err as Error).message);
    }
  };

  return (
    <article className="card question" aria-label={`Answer ${index + 1}`}>
      <div className="question-head">
        <span className="pill">{TYPE_LABELS[q.type]}</span>
        <span className="muted">Q{index + 1}</span>
        <strong className="score">{formatScore(answer.final_score, answer.max_score)}</strong>
      </div>
      <p className="prompt">{q.prompt}</p>
      <h3 className="small-heading">Candidate answer</h3>
      {q.type === "coding" && response ? (
        <pre>{response}</pre>
      ) : (
        <p className="response">{response || "(no answer)"}</p>
      )}
      {q.type === "mcq" && <p className="muted">Correct answer: {q.options[q.correct_index]}</p>}
      {answer.criteria && (
        <table className="table compact">
          <thead>
            <tr>
              <th scope="col">Criterion</th>
              <th scope="col">Score</th>
              <th scope="col">Justification</th>
            </tr>
          </thead>
          <tbody>
            {answer.criteria.map((c) => (
              <tr key={c.name}>
                <td>{c.name}</td>
                <td>
                  {c.score}/{c.max}
                </td>
                <td>{c.justification}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {answer.grading_error && (
        <ErrorBox
          message={`AI grading failed (${answer.grading_error}). Please score this answer yourself.`}
        />
      )}
      <p className="meta">{gradingNote(answer)}</p>
      <form className="row" onSubmit={save}>
        <label className="field field-small">
          <span>Your score (max {answer.max_score})</span>
          <input
            type="number"
            step="0.5"
            min={0}
            max={answer.max_score}
            required
            value={score}
            onChange={(e) => setScore(e.target.value)}
          />
        </label>
        <label className="field grow">
          <span>Note (optional)</span>
          <input value={note} maxLength={500} onChange={(e) => setNote(e.target.value)} />
        </label>
        <button type="submit" className="button-secondary align-end">
          Save override
        </button>
      </form>
      {status && (
        <p className="muted" role="status">
          {status}
        </p>
      )}
      {error && <ErrorBox message={error} />}
    </article>
  );
}

export function ResultsPage() {
  const inviteId = Number(useParams().inviteId);
  const { data, error, reload, setData } = useLoad(() => api.getResult(inviteId), [inviteId]);
  const [polls, setPolls] = useState(0);

  // Grading runs in the background right after submit; poll until it is done.
  useEffect(() => {
    if (data?.invite.status !== "submitted" || polls >= MAX_POLLS) return;
    const timer = window.setTimeout(() => {
      setPolls((n) => n + 1);
      reload();
    }, 2000);
    return () => window.clearTimeout(timer);
  }, [data, reload, polls]);

  if (error && !data) return <ErrorBox message={error} onRetry={reload} />;
  if (!data) return <Loading />;
  const { invite, answers, integrity } = data;
  const graded = invite.status === "graded";
  const total = answers.reduce((sum, a) => sum + (a.final_score ?? 0), 0);
  const max = answers.reduce((sum, a) => sum + a.max_score, 0);
  const updateAnswer = (updated: ResultAnswer) =>
    setData({ ...data, answers: answers.map((a) => (a.id === updated.id ? updated : a)) });

  return (
    <>
      <p>
        <Link to={`/assessments/${data.assessment_id}`}>&larr; {data.assessment_title}</Link>
      </p>
      <div className="title-row">
        <h1>{invite.candidate_name}</h1>
        <Badge status={invite.status} />
      </div>
      <p className="muted">
        {invite.candidate_email} · started {formatDate(invite.started_at)} · submitted{" "}
        {formatDate(invite.submitted_at)}
      </p>
      <div className="stat-row">
        <div className="stat">
          <span className="stat-value">{graded ? formatScore(total, max) : "-"}</span>
          <span className="muted">
            Total score{graded && max ? ` (${Math.round((100 * total) / max)}%)` : ""}
          </span>
        </div>
        {integrity && (
          <div className="stat">
            <span className={`stat-value risk-text-${integrity.risk}`}>{integrity.risk}</span>
            <span className="muted">Integrity risk</span>
          </div>
        )}
      </div>
      {invite.status === "submitted" &&
        (polls < MAX_POLLS ? (
          <Loading label="Grading answers…" />
        ) : (
          <ErrorBox message="Grading is taking longer than usual." onRetry={() => setPolls(0)} />
        ))}
      {integrity ? (
        <IntegrityPanel summary={integrity} result={data} />
      ) : (
        <p className="muted">The candidate has not started yet.</p>
      )}
      <section className="stack" aria-labelledby="answers-heading">
        <h2 id="answers-heading">Answers</h2>
        {answers.length === 0 && <p className="muted">No answers submitted yet.</p>}
        {answers.map((answer, index) => (
          <AnswerReview
            key={`${answer.id}-${answer.graded_by}`}
            answer={answer}
            index={index}
            onUpdated={updateAnswer}
          />
        ))}
      </section>
    </>
  );
}
