import type { PublicQuestion } from "../types";

interface Props {
  question: PublicQuestion;
  name: string;
  value: string;
  onChange: (value: string) => void;
  disabled?: boolean;
}

/** The answer control for one question: radio group for MCQ, textarea otherwise. */
export function AnswerInput({ question, name, value, onChange, disabled }: Props) {
  if (question.type === "mcq") {
    return (
      <fieldset className="options" disabled={disabled}>
        <legend className="visually-hidden">Choose one answer</legend>
        {(question.options ?? []).map((option, index) => (
          <label key={option} className="option">
            <input
              type="radio"
              name={name}
              value={index}
              checked={value === String(index)}
              onChange={() => onChange(String(index))}
            />
            <span>{option}</span>
          </label>
        ))}
      </fieldset>
    );
  }
  const isCode = question.type === "coding";
  return (
    <label className="field">
      <span className="visually-hidden">Your answer</span>
      <textarea
        className={isCode ? "code" : undefined}
        rows={isCode ? 10 : 5}
        value={value}
        disabled={disabled}
        spellCheck={!isCode}
        placeholder={isCode ? `Write your ${question.language ?? "code"} here…` : "Your answer…"}
        onChange={(e) => onChange(e.target.value)}
      />
    </label>
  );
}
