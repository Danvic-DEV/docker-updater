import { useEffect, useMemo, useState } from "react";
import type { ChangeEvent, FormEvent } from "react";

import { createJob, fetchAgents, fetchDockerTargets, fetchJobs } from "./api";
import type { Agent, DockerTarget, Job } from "./types";

const STATUS_CLASS: Record<string, string> = {
  online: "badge badge-online",
  offline: "badge badge-offline",
  queued: "badge badge-queued",
  in_progress: "badge badge-progress",
  completed: "badge badge-done",
  failed: "badge badge-failed",
};

function Badge({ value }: { value: string }) {
  return <span className={STATUS_CLASS[value] ?? "badge"}>{value.replace("_", " ")}</span>;
}

function formatTime(iso: string) {
  return new Date(iso).toLocaleString(undefined, { dateStyle: "short", timeStyle: "medium" });
}

export function App() {
  const [agents, setAgents] = useState<Agent[]>([]);
  const [jobs, setJobs] = useState<Job[]>([]);
  const [targets, setTargets] = useState<DockerTarget[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [form, setForm] = useState<{ target_ref: string; source_type: "registry" | "git"; target_agent_id: string }>({
    target_ref: "",
    source_type: "registry",
    target_agent_id: "",
  });

  const agentMap = useMemo(() => new Map(agents.map((a) => [a.agent_id, a.name])), [agents]);
  const canSubmit = useMemo(() => form.target_ref.trim() && form.target_agent_id.trim(), [form]);
  const sortedJobs = useMemo(() => [...jobs].sort((a, b) => b.created_at.localeCompare(a.created_at)), [jobs]);

  async function refresh() {
    try {
      const [nextAgents, nextJobs, nextTargets] = await Promise.all([fetchAgents(), fetchJobs(), fetchDockerTargets()]);
      setAgents(nextAgents);
      setJobs(nextJobs);
      setTargets(nextTargets);
      setError(null);

      if (!form.target_agent_id && nextAgents[0]) {
        setForm((current) => ({ ...current, target_agent_id: nextAgents[0].agent_id }));
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unknown error");
    }
  }

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!canSubmit) return;
    try {
      await createJob({ ...form });
      setForm((current) => ({ ...current, target_ref: "" }));
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create job");
    }
  }

  useEffect(() => {
    refresh();
    const id = window.setInterval(refresh, 5000);
    return () => window.clearInterval(id);
  }, []);

  function onTargetRefChange(event: ChangeEvent<HTMLInputElement>) {
    setForm((curr) => ({ ...curr, target_ref: event.target.value }));
  }

  function onSourceTypeChange(event: ChangeEvent<HTMLSelectElement>) {
    setForm((curr) => ({ ...curr, source_type: event.target.value === "git" ? "git" : "registry" }));
  }

  function onAgentChange(event: ChangeEvent<HTMLSelectElement>) {
    setForm((curr) => ({ ...curr, target_agent_id: event.target.value }));
  }

  function selectTarget(target: DockerTarget) {
    setForm((curr) => ({ ...curr, target_ref: target.image, source_type: "registry" }));
  }

  return (
    <main className="layout">
      <header className="header">
        <h1>Docker Updater</h1>
        <button onClick={refresh}>Refresh</button>
      </header>

      {error ? <section className="error">{error}</section> : null}

      <section className="grid">
        <article className="card">
          <h2>Dispatch Update</h2>
          <form onSubmit={onSubmit} className="form">
            <label>
              Image / Tag
              <input
                value={form.target_ref}
                onChange={onTargetRefChange}
                placeholder="nginx:1.27 — or click a container below"
              />
            </label>

            <label>
              Source
              <select value={form.source_type} onChange={onSourceTypeChange}>
                <option value="registry">Registry</option>
                <option value="git">Git</option>
              </select>
            </label>

            <label>
              Agent
              <select value={form.target_agent_id} onChange={onAgentChange}>
                {agents.map((agent) => (
                  <option key={agent.agent_id} value={agent.agent_id}>
                    {agent.name} — {agent.status}
                  </option>
                ))}
              </select>
            </label>

            <button type="submit" disabled={!canSubmit}>
              Run Update
            </button>
          </form>
        </article>

        <article className="card">
          <h2>Agents</h2>
          <ul className="list">
            {agents.length === 0 ? <li className="empty">No agents registered yet</li> : null}
            {agents.map((agent) => (
              <li key={agent.agent_id}>
                <div>
                  <strong>{agent.name}</strong>
                  <small className="muted">{agent.agent_id}</small>
                </div>
                <Badge value={agent.status} />
              </li>
            ))}
          </ul>
        </article>

        <article className="card wide">
          <h2>Running Containers <small className="muted">(click to pre-fill)</small></h2>
          <ul className="targets">
            {targets.length === 0 ? <li className="empty">No running containers detected</li> : null}
            {targets.map((target) => (
              <li key={target.id} className="target-row" onClick={() => selectTarget(target)} title="Click to pre-fill image">
                <strong>{target.name}</strong>
                <span className="image-tag">{target.image}</span>
                <Badge value={target.status} />
              </li>
            ))}
          </ul>
        </article>

        <article className="card wide">
          <h2>Jobs</h2>
          <ul className="jobs">
            {sortedJobs.length === 0 ? <li className="empty">No jobs yet</li> : null}
            {sortedJobs.map((job) => (
              <li key={job.job_id}>
                <div className="job-header">
                  <div>
                    <strong>{job.target_ref}</strong>
                    <span className="muted"> → {agentMap.get(job.target_agent_id) ?? job.target_agent_id}</span>
                  </div>
                  <div className="job-meta">
                    <Badge value={job.status} />
                    <small className="muted">{formatTime(job.created_at)}</small>
                  </div>
                </div>
                <details>
                  <summary>Logs ({job.logs.length})</summary>
                  <pre>{job.logs.join("\n") || "No logs yet"}</pre>
                </details>
              </li>
            ))}
          </ul>
        </article>
      </section>
    </main>
  );
}
