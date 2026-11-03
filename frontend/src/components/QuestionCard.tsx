import { type FormEvent, useState } from "react";
import { TYPE_LABELS } from "../lib/format";
import type { Question, RubricCriterion } from "../types";
import { ErrorBox } from "./Status";

function points(question: Question): number {
  return question.type === "mcq" ? 1 : question.rubric.reduce((sum, c) => sum + c.points, 0);
}

export function RubricTable({ rubric }: { rubric: RubricCriterion[] }) {
  return (
    <table className="table compact">
      <thead>
        <tr>
          <th scope="col">Criterion</th>
          <th scope="col">What earns the points</th>
          <th scope="col">Points</th>
        </tr>
      </thead>
      <tbody>
        {rubric.map((c) => (
          <tr key={c.name}>
            <td>{c.name}</td>
            <td>{c.description}</td>
            <td>{c.points}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

/** Read-only view of a question with its answer key (recruiter only). */
export function QuestionView({ question, index }: { question: Question; index: number }) {
  return (
    <>
      <div className="question-head">
        <span className="pill">{TYPE_LABELS[question.type]}</span>
        <span className="muted">
          Q{index + 1} · {points(question)} pt
        </span>
      </div>
      <p className="prompt">{question.prompt}</p>
      {question.type === "mcq" && (
        <>
          <ol className="answer-key">
            {question.options.map((option, i) => (
              <li key={option} className={i === question.correct_index ? "correct" : undefined}>
                {option}
                {i === question.correct_index && <strong> - correct</strong>}
              </li>
            ))}
          </ol>
          <p className="muted">{question.explanation}</p>
        </>
      )}
      {question.type !== "mcq" && (
        <details>
          <summary>{question.type === "coding" ? "Reference solution" : "Model answer"} and rubric</summary>
          {question.type === "coding" ? (
            <pre>{question.reference_solution}</pre>
          ) : (
            <p>{question.model_answer}</p>
          )}
          <RubricTable rubric={question.rubric} />
        </details>
      )}
    </>
  );
}

function RubricEditor({
  rubric,
  onChange,
}: {
  rubric: RubricCriterion[];
  onChange: (r: RubricCriterion[]) => void;
}) {
  const update = (i: number, patch: Partial<RubricCriterion>) =>
    onChange(rubric.map((c, j) => (j === i ? { ...c, ...patch } : c)));
  return (
    <fieldset className="stack">
      <legend>Rubric</legend>
      {rubric.map((c, i) => (
        <div className="row" key={i}>
          <input
            aria-label={`Criterion ${i + 1} name`}
            value={c.name}
            onChange={(e) => update(i, { name: e.target.value })}
          />
          <input
            className="grow"
            aria-label={`Criterion ${i + 1} description`}
            value={c.description}
            onChange={(e) => update(i, { description: e.target.value })}
          />
          <input
            type="number"
            min={1}
            max={10}
            className="narrow"
            aria-label={`Criterion ${i + 1} points`}
            value={c.points}
            onChange={(e) => update(i, { points: Number(e.target.value) })}
          />
          <button
            type="button"
            className="button-secondary"
            onClick={() => onChange(rubric.filter((_, j) => j !== i))}
            disabled={rubric.length === 1}
          >
            Remove
          </button>
        </div>
      ))}
      <div>
        <button
          type="button"
          className="button-secondary"
          onClick={() => onChange([...rubric, { name: "", description: "", points: 1 }])}
        >
          Add criterion
        </button>
      </div>
    </fieldset>
  );
}

function QuestionEditor({
  value,
  onSave,
  onCancel,
}: {
  value: Question;
  onSave: (q: Question) => Promise<void>;
  onCancel: () => void;
}) {
  const [q, setQ] = useState<Question>(value);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const set = (patch: object) => setQ({ ...q, ...patch } as Question);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await onSave(q);
    } catch (err) {
      setError((err as Error).message);
      setBusy(false);
    }
  };

  return (
    <form className="stack" onSubmit={submit}>
      <label className="field">
        <span>Question</span>
        <textarea rows={3} value={q.prompt} onChange={(e) => set({ prompt: e.target.value })} />
      </label>
      {q.type === "mcq" && (
        <>
          <fieldset className="stack">
            <legend>Options (select the correct one)</legend>
            {q.options.map((option, i) => (
              <div className="row" key={i}>
                <input
                  type="radio"
                  name="correct"
                  checked={q.correct_index === i}
                  onChange={() => set({ correct_index: i })}
                  aria-label={`Option ${i + 1} is correct`}
                />
                <input
                  className="grow"
                  aria-label={`Option ${i + 1}`}
                  value={option}
                  onChange={(e) => set({ options: q.options.map((o, j) => (j === i ? e.target.value : o)) })}
                />
              </div>
            ))}
          </fieldset>
          <label className="field">
            <span>Explanation</span>
            <textarea rows={2} value={q.explanation} onChange={(e) => set({ explanation: e.target.value })} />
          </label>
        </>
      )}
      {q.type === "short_answer" && (
        <label className="field">
          <span>Model answer</span>
          <textarea rows={3} value={q.model_answer} onChange={(e) => set({ model_answer: e.target.value })} />
        </label>
      )}
      {q.type === "coding" && (
        <>
          <label className="field field-small">
            <span>Language</span>
            <input value={q.language} onChange={(e) => set({ language: e.target.value })} />
          </label>
          <label className="field">
            <span>Reference solution</span>
            <textarea
              className="code"
              rows={8}
              value={q.reference_solution}
              onChange={(e) => set({ reference_solution: e.target.value })}
            />
          </label>
        </>
      )}
      {q.type !== "mcq" && <RubricEditor rubric={q.rubric} onChange={(rubric) => set({ rubric })} />}
      {error && <ErrorBox message={error} />}
      <div className="row">
        <button type="submit" disabled={busy}>
          {busy ? "Saving…" : "Save question"}
        </button>
        <button type="button" className="button-secondary" onClick={onCancel}>
          Cancel
        </button>
      </div>
    </form>
  );
}

interface CardProps {
  question: Question;
  index: number;
  editable: boolean;
  onSave: (q: Question) => Promise<void>;
  onDelete: () => Promise<void>;
}

export function QuestionCard({ question, index, editable, onSave, onDelete }: CardProps) {
  const [editing, setEditing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const save = async (q: Question) => {
    await onSave(q);
    setEditing(false);
  };
  const remove = () => onDelete().catch((err: Error) => setError(err.message));

  return (
    <article className="card question" aria-label={`Question ${index + 1}`}>
      {editing ? (
        <QuestionEditor value={question} onSave={save} onCancel={() => setEditing(false)} />
      ) : (
        <>
          <QuestionView question={question} index={index} />
          {error && <ErrorBox message={error} />}
          {editable && (
            <div className="row">
              <button type="button" className="button-secondary" onClick={() => setEditing(true)}>
                Edit
              </button>
              <button type="button" className="button-danger" onClick={remove}>
                Delete
              </button>
            </div>
          )}
        </>
      )}
    </article>
  );
}
