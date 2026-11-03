import { type FormEvent, useState } from "react";
import { parseSkills } from "../lib/format";
import type { Difficulty, GenerationRequest } from "../types";

interface Props {
  /** Recruiters pick skills; learners mostly paste notes. */
  variant: "hiring" | "practice";
  busy: boolean;
  onSubmit: (request: GenerationRequest) => void;
}

export function GenerationForm({ variant, busy, onSubmit }: Props) {
  const [topic, setTopic] = useState("");
  const [skills, setSkills] = useState("");
  const [material, setMaterial] = useState("");
  const [difficulty, setDifficulty] = useState<Difficulty>("medium");
  const [mix, setMix] = useState(
    variant === "hiring" ? { mcq: 3, short_answer: 1, coding: 1 } : { mcq: 4, short_answer: 1, coding: 0 },
  );

  const submit = (event: FormEvent) => {
    event.preventDefault();
    onSubmit({ topic, skills: parseSkills(skills), difficulty, mix, source_material: material });
  };
  const counter = (key: keyof typeof mix, label: string, max: number) => (
    <label className="field field-small">
      <span>{label}</span>
      <input
        type="number"
        min={0}
        max={max}
        value={mix[key]}
        onChange={(e) => setMix({ ...mix, [key]: Number(e.target.value) })}
      />
    </label>
  );

  return (
    <form className="stack" onSubmit={submit}>
      <div className="row">
        <label className="field grow">
          <span>Topic</span>
          <input
            value={topic}
            onChange={(e) => setTopic(e.target.value)}
            placeholder="e.g. Backend engineering"
          />
        </label>
        {variant === "hiring" && (
          <label className="field grow">
            <span>Skills (comma separated)</span>
            <input
              value={skills}
              onChange={(e) => setSkills(e.target.value)}
              placeholder="Python, SQL, REST APIs"
            />
          </label>
        )}
      </div>
      <label className="field">
        <span>{variant === "practice" ? "Study notes" : "Source material (optional)"}</span>
        <textarea
          rows={variant === "practice" ? 8 : 4}
          value={material}
          onChange={(e) => setMaterial(e.target.value)}
          placeholder="Paste notes or a document; questions will be based only on it."
        />
      </label>
      <div className="row">
        <label className="field field-small">
          <span>Difficulty</span>
          <select value={difficulty} onChange={(e) => setDifficulty(e.target.value as Difficulty)}>
            <option value="easy">Easy</option>
            <option value="medium">Medium</option>
            <option value="hard">Hard</option>
          </select>
        </label>
        {counter("mcq", "Multiple choice", 20)}
        {counter("short_answer", "Short answer", 10)}
        {counter("coding", "Coding", 5)}
      </div>
      <div>
        <button type="submit" disabled={busy}>
          {busy ? "Generating…" : variant === "practice" ? "Make my quiz" : "Generate questions"}
        </button>
      </div>
    </form>
  );
}
