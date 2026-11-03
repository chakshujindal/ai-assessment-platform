import { type FormEvent, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api } from "../api";
import { GenerationForm } from "../components/GenerationForm";
import { QuestionCard } from "../components/QuestionCard";
import { Badge, ErrorBox, Loading } from "../components/Status";
import { formatDate, formatScore } from "../lib/format";
import { useLoad } from "../lib/useLoad";
import type { Assessment, AssessmentSettings, GenerationRequest, InviteCreated } from "../types";

function SettingsForm({ assessment, onSaved }: { assessment: Assessment; onSaved: (a: Assessment) => void }) {
  const [form, setForm] = useState<AssessmentSettings>(assessment);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const set = (patch: Partial<AssessmentSettings>) => setForm({ ...form, ...patch });

  const save = async (event: FormEvent) => {
    event.preventDefault();
    setError(null);
    try {
      onSaved(await api.updateAssessment(assessment.id, form));
      setMessage("Settings saved.");
    } catch (err) {
      setError((err as Error).message);
    }
  };

  return (
    <section className="card">
      <h2>Settings</h2>
      <form className="stack" onSubmit={save}>
        <div className="row">
          <label className="field grow">
            <span>Title</span>
            <input required value={form.title} onChange={(e) => set({ title: e.target.value })} />
          </label>
          <label className="field field-small">
            <span>Time limit (minutes)</span>
            <input
              type="number"
              min={1}
              max={240}
              value={form.duration_minutes}
              onChange={(e) => set({ duration_minutes: Number(e.target.value) })}
            />
          </label>
          <label className="field field-small">
            <span>Webcam snapshot every (s, 0 = off)</span>
            <input
              type="number"
              min={0}
              max={600}
              value={form.snapshot_interval_seconds}
              onChange={(e) => set({ snapshot_interval_seconds: Number(e.target.value) })}
            />
          </label>
        </div>
        <label className="check">
          <input
            type="checkbox"
            checked={form.require_seb}
            onChange={(e) => set({ require_seb: e.target.checked })}
          />
          Require Safe Exam Browser
        </label>
        {form.require_seb && (
          <label className="field">
            <span>Browser Exam Key (from the SEB config tool)</span>
            <input
              className="code"
              value={form.seb_browser_exam_key ?? ""}
              onChange={(e) => set({ seb_browser_exam_key: e.target.value })}
            />
          </label>
        )}
        {error && <ErrorBox message={error} />}
        {message && (
          <p className="muted" role="status">
            {message}
          </p>
        )}
        <div>
          <button type="submit" className="button-secondary">
            Save settings
          </button>
        </div>
      </form>
    </section>
  );
}

function GeneratePanel({ assessmentId, onAdded }: { assessmentId: number; onAdded: () => void }) {
  const [busy, setBusy] = useState(false);
  const [summary, setSummary] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const generate = async (request: GenerationRequest) => {
    setBusy(true);
    setError(null);
    setSummary(null);
    try {
      const result = await api.generate(assessmentId, request);
      setSummary(
        `Added ${result.added.length} question(s), removed ${result.duplicates_removed} near-duplicate(s). ` +
          `Model ${result.model_name}, prompt ${result.prompt_version}.`,
      );
      onAdded();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="card">
      <h2>Generate questions with AI</h2>
      <GenerationForm variant="hiring" busy={busy} onSubmit={generate} />
      {summary && (
        <p className="alert alert-info" role="status">
          {summary}
        </p>
      )}
      {error && <ErrorBox message={error} />}
    </section>
  );
}

function InvitePanel({ assessmentId }: { assessmentId: number }) {
  const invites = useLoad(() => api.listInvites(assessmentId), [assessmentId]);
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [created, setCreated] = useState<InviteCreated | null>(null);
  const [copied, setCopied] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const link = created ? `${window.location.origin}${created.link_path}` : "";

  const invite = async (event: FormEvent) => {
    event.preventDefault();
    setError(null);
    try {
      setCreated(await api.createInvite(assessmentId, { candidate_name: name, candidate_email: email }));
      setCopied(false);
      setName("");
      setEmail("");
      invites.reload();
    } catch (err) {
      setError((err as Error).message);
    }
  };
  const copy = () =>
    navigator.clipboard.writeText(link).then(
      () => setCopied(true),
      () => setError("Could not copy automatically; select the link and copy it."),
    );

  return (
    <section className="card">
      <h2>Invite candidates</h2>
      <form className="row" onSubmit={invite}>
        <label className="field grow">
          <span>Candidate name</span>
          <input required value={name} onChange={(e) => setName(e.target.value)} />
        </label>
        <label className="field grow">
          <span>Candidate email</span>
          <input type="email" required value={email} onChange={(e) => setEmail(e.target.value)} />
        </label>
        <button type="submit" className="align-end">
          Create invite link
        </button>
      </form>
      {error && <ErrorBox message={error} />}
      {created && (
        <div className="alert alert-success" role="status">
          <p>Single-use link for {created.candidate_name}. It is shown only once, so copy it now:</p>
          <div className="row">
            <code className="link-box" data-testid="invite-link">
              {link}
            </code>
            <button type="button" className="button-secondary" onClick={copy}>
              {copied ? "Copied" : "Copy link"}
            </button>
          </div>
        </div>
      )}
      <h3>Candidates</h3>
      {invites.loading && !invites.data && <Loading />}
      {invites.error && <ErrorBox message={invites.error} onRetry={invites.reload} />}
      {invites.data?.length === 0 && <p className="muted">No candidates invited yet.</p>}
      {!!invites.data?.length && (
        <table className="table">
          <thead>
            <tr>
              <th scope="col">Name</th>
              <th scope="col">Status</th>
              <th scope="col">Score</th>
              <th scope="col">Link expires</th>
              <th scope="col">
                <span className="visually-hidden">Actions</span>
              </th>
            </tr>
          </thead>
          <tbody>
            {invites.data.map((inv) => (
              <tr key={inv.id}>
                <td>
                  {inv.candidate_name}
                  <div className="muted small">{inv.candidate_email}</div>
                </td>
                <td>
                  <Badge status={inv.status} />
                </td>
                <td>{formatScore(inv.score, inv.max_score)}</td>
                <td>{formatDate(inv.expires_at)}</td>
                <td>{inv.started_at && <Link to={`/results/${inv.id}`}>View results</Link>}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}

export function BuilderPage() {
  const id = Number(useParams().id);
  const { data: assessment, error, reload, setData } = useLoad(() => api.getAssessment(id), [id]);
  const [publishError, setPublishError] = useState<string | null>(null);

  if (error && !assessment) return <ErrorBox message={error} onRetry={reload} />;
  if (!assessment) return <Loading />;
  const draft = assessment.status === "draft";
  const publish = () => api.publish(id).then(setData, (err: Error) => setPublishError(err.message));

  return (
    <>
      <p>
        <Link to="/">&larr; All assessments</Link>
      </p>
      <div className="title-row">
        <h1>{assessment.title}</h1>
        <Badge status={assessment.status} />
      </div>
      {draft ? (
        <SettingsForm assessment={assessment} onSaved={setData} />
      ) : (
        <p className="muted">
          {assessment.duration_minutes} minutes ·{" "}
          {assessment.snapshot_interval_seconds
            ? `webcam snapshot every ${assessment.snapshot_interval_seconds}s`
            : "no webcam"}
          {assessment.require_seb && " · Safe Exam Browser required"}
        </p>
      )}
      {draft && <GeneratePanel assessmentId={id} onAdded={reload} />}
      <section className="card">
        <h2>Questions ({assessment.questions.length})</h2>
        {assessment.questions.length === 0 && <p className="muted">No questions yet. Generate some above.</p>}
        <div className="stack">
          {assessment.questions.map((row, index) => (
            <QuestionCard
              key={row.id}
              question={row.question}
              index={index}
              editable={draft}
              onSave={async (q) => setData(await api.editQuestion(id, row.id, q))}
              onDelete={async () => {
                await api.deleteQuestion(id, row.id);
                reload();
              }}
            />
          ))}
        </div>
        {draft && (
          <div className="publish-bar">
            <p className="muted">Publishing locks the questions so every candidate gets the same test.</p>
            <button type="button" onClick={publish} disabled={assessment.questions.length === 0}>
              Publish
            </button>
          </div>
        )}
        {publishError && <ErrorBox message={publishError} />}
      </section>
      {!draft && <InvitePanel assessmentId={id} />}
    </>
  );
}
