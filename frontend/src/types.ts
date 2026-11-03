// Shapes returned by the FastAPI backend (see backend/app/schemas.py).

export type QuestionType = "mcq" | "short_answer" | "coding";
export type Difficulty = "easy" | "medium" | "hard";

export interface RubricCriterion {
  name: string;
  description: string;
  points: number;
}

export interface MCQQuestion {
  type: "mcq";
  prompt: string;
  options: string[];
  correct_index: number;
  explanation: string;
}

export interface ShortAnswerQuestion {
  type: "short_answer";
  prompt: string;
  model_answer: string;
  rubric: RubricCriterion[];
}

export interface CodingQuestion {
  type: "coding";
  prompt: string;
  language: string;
  reference_solution: string;
  rubric: RubricCriterion[];
}

export type Question = MCQQuestion | ShortAnswerQuestion | CodingQuestion;

export interface QuestionRow {
  id: number;
  position: number;
  question: Question;
}

export interface AssessmentSettings {
  title: string;
  duration_minutes: number;
  snapshot_interval_seconds: number;
  require_seb: boolean;
  seb_browser_exam_key: string | null;
}

export interface Assessment extends AssessmentSettings {
  id: number;
  status: "draft" | "published";
  created_at: string;
  questions: QuestionRow[];
}

export interface AssessmentSummary {
  id: number;
  title: string;
  status: string;
  duration_minutes: number;
  question_count: number;
  invite_count: number;
  created_at: string;
}

export interface GenerationRequest {
  topic: string;
  skills: string[];
  difficulty: Difficulty;
  mix: { mcq: number; short_answer: number; coding: number };
  source_material: string;
}

export interface GenerateResult {
  added: QuestionRow[];
  duplicates_removed: number;
  model_name: string;
  prompt_version: string;
}

export interface Invite {
  id: number;
  candidate_name: string;
  candidate_email: string;
  status: string;
  expires_at: string;
  started_at: string | null;
  submitted_at: string | null;
  score: number | null;
  max_score: number | null;
}

export interface InviteCreated extends Invite {
  token: string;
  link_path: string;
}

export interface CriterionScore {
  name: string;
  score: number;
  max: number;
  justification: string;
}

export interface ResultAnswer {
  id: number;
  question_id: number;
  question: Question;
  response: string;
  max_score: number;
  ai_score: number | null;
  final_score: number | null;
  criteria: CriterionScore[] | null;
  feedback: string | null;
  graded_by: string | null;
  model_name: string | null;
  prompt_version: string | null;
  grading_error: string | null;
  override_score: number | null;
  override_note: string | null;
}

export interface IntegritySummary {
  risk: "low" | "medium" | "high";
  flags: { level: "info" | "warning"; message: string }[];
  counts: Record<string, number>;
  time_away_seconds: number;
  snapshots_received: number;
  snapshots_expected: number;
  timeline: { kind: string; at: string; offset_seconds: number; detail: string }[];
}

export interface Result {
  assessment_id: number;
  assessment_title: string;
  invite: Invite;
  answers: ResultAnswer[];
  integrity: IntegritySummary | null;
  snapshots: { id: number; taken_at: string }[];
}

export interface TakeInfo {
  assessment_title: string;
  candidate_name: string;
  status: string;
  duration_minutes: number;
  question_count: number;
  snapshot_interval_seconds: number;
  remaining_seconds: number | null;
}

/** A question as a candidate or learner sees it: no answers or rubric. */
export interface PublicQuestion {
  type: QuestionType;
  prompt: string;
  points: number;
  options: string[] | null;
  language: string | null;
}

export interface TestPaper {
  questions: (PublicQuestion & { id: number })[];
  remaining_seconds: number;
  snapshot_interval_seconds: number;
}

export interface PracticeQuiz {
  id: string;
  questions: (PublicQuestion & { index: number })[];
  duplicates_removed: number;
}

export interface CheckResult {
  score: number;
  max_score: number;
  correct: boolean | null;
  feedback: string;
  criteria: CriterionScore[] | null;
  reference: string;
}
