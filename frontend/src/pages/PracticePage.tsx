import { useState } from "react";
import { api } from "../api";
import { AnswerInput } from "../components/AnswerInput";
import { GenerationForm } from "../components/GenerationForm";
import { ErrorBox } from "../components/Status";
import { TYPE_LABELS } from "../lib/format";
import type { CheckResult, GenerationRequest, PracticeQuiz } from "../types";

function Feedback({ result }: { result: CheckResult }) {
  const verdict =
    result.correct === null
      ? `Score: ${result.score} / ${result.max_score}`
      : result.correct
        ? "Correct!"
        : "Not quite.";
  const tone =
    result.correct === false || (result.correct === null && result.score < result.max_score / 2)
      ? "warn"
      : "good";
  return (
    <div className={`feedback feedback-${tone}`} role="status">
      <strong>{verdict}</strong>
      {result.criteria ? (
        <ul>
          {result.criteria.map((c) => (
            <li key={c.name}>
              {c.name} ({c.score}/{c.max}): {c.justification}
            </li>
          ))}
        </ul>
      ) : (
        <p>{result.feedback.replace(/^(Correct|Incorrect)\.\s*/, "")}</p>
      )}
      <details>
        <summary>{result.correct === null ? "Model answer" : "Correct answer"}</summary>
        <pre>{result.reference}</pre>
      </details>
    </div>
  );
}

function PracticeQuestion({
  quizId,
  question,
}: {
  quizId: string;
  question: PracticeQuiz["questions"][number];
}) {
  const [answer, setAnswer] = useState("");
  const [result, setResult] = useState<CheckResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const check = async () => {
    setBusy(true);
    setError(null);
    try {
      setResult(await api.checkPractice(quizId, question.index, answer));
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="card question" aria-labelledby={`pq-${question.index}`}>
      <div className="question-head">
        <span className="pill">{TYPE_LABELS[question.type]}</span>
      </div>
      <p id={`pq-${question.index}`} className="prompt">
        {question.index + 1}. {question.prompt}
      </p>
      <AnswerInput
        question={question}
        name={`pq-${question.index}`}
        value={answer}
        onChange={setAnswer}
        disabled={!!result}
      />
      <div className="row">
        {result ? (
          <button type="button" className="button-secondary" onClick={() => setResult(null)}>
            Try again
          </button>
        ) : (
          <button type="button" onClick={check} disabled={busy || !answer.trim()}>
            {busy ? "Checking…" : "Check answer"}
          </button>
        )}
      </div>
      {error && <ErrorBox message={error} />}
      {result && <Feedback result={result} />}
    </section>
  );
}

export function PracticePage() {
  const [quiz, setQuiz] = useState<PracticeQuiz | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const create = async (request: GenerationRequest) => {
    setBusy(true);
    setError(null);
    try {
      setQuiz(await api.createPractice(request));
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      <h1>Practice</h1>
      <p className="muted">
        Paste your study notes or name a topic. You get a quiz with instant feedback on every answer. No
        account needed.
      </p>
      {!quiz && (
        <section className="card">
          <GenerationForm variant="practice" busy={busy} onSubmit={create} />
          {error && <ErrorBox message={error} />}
        </section>
      )}
      {quiz && (
        <div className="stack">
          {quiz.questions.length === 0 && (
            <p className="muted">No questions could be made from that input. Try more detailed notes.</p>
          )}
          {quiz.questions.map((q) => (
            <PracticeQuestion key={`${quiz.id}-${q.index}`} quizId={quiz.id} question={q} />
          ))}
          <div>
            <button type="button" className="button-secondary" onClick={() => setQuiz(null)}>
              Start a new quiz
            </button>
          </div>
        </div>
      )}
    </>
  );
}
