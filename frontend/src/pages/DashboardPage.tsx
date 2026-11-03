import { type FormEvent, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api } from "../api";
import { Badge, ErrorBox, Loading } from "../components/Status";
import { formatDate } from "../lib/format";
import { useLoad } from "../lib/useLoad";

export function DashboardPage() {
  const navigate = useNavigate();
  const { data, error, loading, reload } = useLoad(api.listAssessments, []);
  const [title, setTitle] = useState("");
  const [createError, setCreateError] = useState<string | null>(null);

  const create = async (event: FormEvent) => {
    event.preventDefault();
    try {
      const assessment = await api.createAssessment({ title });
      navigate(`/assessments/${assessment.id}`);
    } catch (err) {
      setCreateError((err as Error).message);
    }
  };

  return (
    <>
      <h1>Assessments</h1>
      <section className="card">
        <h2>New assessment</h2>
        <form className="row" onSubmit={create}>
          <label className="field grow">
            <span>Title</span>
            <input
              required
              maxLength={200}
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="e.g. Data Engineer screening"
            />
          </label>
          <button type="submit" className="align-end">
            Create
          </button>
        </form>
        {createError && <ErrorBox message={createError} />}
      </section>
      <section className="card">
        <h2>Your assessments</h2>
        {loading && <Loading />}
        {error && <ErrorBox message={error} onRetry={reload} />}
        {data && data.length === 0 && <p className="muted">No assessments yet. Create one above.</p>}
        {data && data.length > 0 && (
          <table className="table">
            <thead>
              <tr>
                <th scope="col">Title</th>
                <th scope="col">Status</th>
                <th scope="col">Questions</th>
                <th scope="col">Candidates</th>
                <th scope="col">Created</th>
              </tr>
            </thead>
            <tbody>
              {data.map((a) => (
                <tr key={a.id}>
                  <td>
                    <Link to={`/assessments/${a.id}`}>{a.title}</Link>
                  </td>
                  <td>
                    <Badge status={a.status} />
                  </td>
                  <td>{a.question_count}</td>
                  <td>{a.invite_count}</td>
                  <td>{formatDate(a.created_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
    </>
  );
}
