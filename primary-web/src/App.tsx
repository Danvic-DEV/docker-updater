import { useEffect, useMemo, useState } from "react";
import type { ChangeEvent, FormEvent } from "react";

import { createAgentBootstrapCommand, createJob, fetchAgents, fetchDockerTargets, fetchJobs } from "./api";
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
  const [page, setPage] = useState<'home' | 'settings'>('home');
  const [agents, setAgents] = useState<Agent[]>([]);
  const [jobs, setJobs] = useState<Job[]>([]);
  const [targets, setTargets] = useState<DockerTarget[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [bootstrap, setBootstrap] = useState<{ command: string; expires_at: string } | null>(null);
  const [copied, setCopied] = useState(false);
  const [onboardingForm, setOnboardingForm] = useState<{ agent_id: string; agent_name: string; primary_api_base_url: string; agent_image: string }>({
    agent_id: "",
    agent_name: "",
    primary_api_base_url: "",
    agent_image: "ghcr.io/danvic-dev/docker-updater-agent:latest",
  });
  const [form, setForm] = useState<{ target_ref: string; source_type: "registry" | "git"; target_agent_id: string }>({
    target_ref: "",
    source_type: "registry",
    target_agent_id: "",
  });

  const agentMap = useMemo(() => new Map(agents.map((a) => [a.agent_id, a.name])), [agents]);
  const canSubmit = useMemo(() => form.target_ref.trim() && form.target_agent_id.trim(), [form]);
  const canGenerateBootstrap = useMemo(
    () => onboardingForm.agent_id.trim() && onboardingForm.agent_name.trim(),
    [onboardingForm]
  );
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

      if (!onboardingForm.primary_api_base_url) {
        setOnboardingForm((current) => ({ ...current, primary_api_base_url: `${window.location.protocol}//${window.location.hostname}:8000` }));
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

  function onOnboardingFieldChange(event: ChangeEvent<HTMLInputElement>) {
    setOnboardingForm((curr) => ({ ...curr, [event.target.name]: event.target.value }));
  }

  async function onGenerateBootstrapCommand(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!canGenerateBootstrap) return;

    try {
      const response = await createAgentBootstrapCommand({
        agent_id: onboardingForm.agent_id.trim(),
        agent_name: onboardingForm.agent_name.trim(),
        primary_api_base_url: onboardingForm.primary_api_base_url.trim() || undefined,
        agent_image: onboardingForm.agent_image.trim() || undefined,
      });
      setBootstrap({ command: response.command, expires_at: response.expires_at });
      setCopied(false);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to generate command");
    }
  }

  async function copyCommand() {
    if (!bootstrap) return;
    await navigator.clipboard.writeText(bootstrap.command);
    setCopied(true);
  }

  const agentsOnline = agents.filter((a) => a.status === "online").length;
  const agentsOffline = agents.filter((a) => a.status === "offline").length;
  const jobsComplete = jobs.filter((j) => j.status === "completed").length;
  const jobsFailed = jobs.filter((j) => j.status === "failed").length;
  const jobsInProgress = jobs.filter((j) => j.status === "in_progress").length;

  return (
    <main className="layout">
      <header className="header">
        <h1 style={{ cursor: 'pointer' }} onClick={() => setPage('home')}>Docker Updater</h1>
        <div className="header-actions">
          <button onClick={refresh} title="Refresh">{page === 'home' ? '↻' : ''}</button>
          <button onClick={() => setPage(page === 'home' ? 'settings' : 'home')} title={page === 'home' ? 'Settings' : 'Home'}>
            {page === 'home' ? '⚙' : '⌂'}
          </button>
        </div>
      </header>

      {error ? <section className="error">{error}</section> : null}

      {page === 'settings' && (
        <section className="settings-page">
          <article className="card onboarding">
            <h2>Add Agent</h2>
            <p className="muted">Generate install command for new agent.</p>
            <form onSubmit={onGenerateBootstrapCommand} className="form">
              <label>
                Agent ID
                <input
                  name="agent_id"
                  value={onboardingForm.agent_id}
                  onChange={onOnboardingFieldChange}
                  placeholder="living-room-nas"
                />
              </label>

              <label>
                Agent Name
                <input
                  name="agent_name"
                  value={onboardingForm.agent_name}
                  onChange={onOnboardingFieldChange}
                  placeholder="Living Room NAS"
                />
              </label>

              <label>
                Primary API URL
                <input
                  name="primary_api_base_url"
                  value={onboardingForm.primary_api_base_url}
                  onChange={onOnboardingFieldChange}
                  placeholder="http://192.168.1.10:8000"
                />
              </label>

              <label>
                Agent Image
                <input
                  name="agent_image"
                  value={onboardingForm.agent_image}
                  onChange={onOnboardingFieldChange}
                  placeholder="ghcr.io/danvic-dev/docker-updater-agent:latest"
                />
              </label>

              <button type="submit" disabled={!canGenerateBootstrap}>
                Generate Command
              </button>
            </form>

            {bootstrap ? (
              <div className="command-box">
                <div className="command-header">
                  <small className="muted">Expires: {formatTime(bootstrap.expires_at)}</small>
                  <button type="button" onClick={copyCommand}>{copied ? '✓ Copied' : 'Copy'}</button>
                </div>
                <pre>{bootstrap.command}</pre>
              </div>
            ) : null}
          </article>
        </section>
      )}

      {page === 'home' && (
        <>
      {/* Dashboard Stats */}
      <section className="dashboard-stats">
        <div className="stat-card">
          <div className="stat-value">{agentsOnline}</div>
          <div className="stat-label">Agents Online</div>
        </div>
        <div className="stat-card">
          <div className="stat-value">{agentsOffline}</div>
          <div className="stat-label">Agents Offline</div>
        </div>
        <div className="stat-card">
          <div className="stat-value">{jobsComplete}</div>
          <div className="stat-label">Jobs Completed</div>
        </div>
        <div className="stat-card">
          <div className="stat-value">{jobsFailed}</div>
          <div className="stat-label">Jobs Failed</div>
        </div>
        <div className="stat-card">
          <div className="stat-value">{jobsInProgress}</div>
          <div className="stat-label">In Progress</div>
        </div>
        <div className="stat-card">
          <div className="stat-value">{targets.length}</div>
          <div className="stat-label">Running Containers</div>
        </div>
      </section>

      <section className="main-grid">
        {/* Left: Dispatch & Agents */}
        <aside className="sidebar">
          <article className="card">
            <h2>Dispatch Update</h2>
            <form onSubmit={onSubmit} className="form">
              <label>
                Image / Tag
                <input
                  value={form.target_ref}
                  onChange={onTargetRefChange}
                  placeholder="nginx:1.27"
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
                  {agents.length === 0 ? (
                    <option disabled>No agents online</option>
                  ) : (
                    agents.map((agent) => (
                      <option key={agent.agent_id} value={agent.agent_id}>
                        {agent.name}
                      </option>
                    ))
                  )}
                </select>
              </label>

              <button type="submit" disabled={!canSubmit}>
                Run Update
              </button>
            </form>
          </article>

          <article className="card">
            <h2>Agents</h2>
            <table className="table">
              <tbody>
                {agents.length === 0 ? (
                  <tr>
                    <td colSpan={2} className="empty">
                      No agents registered
                    </td>
                  </tr>
                ) : (
                  agents.map((agent) => (
                    <tr key={agent.agent_id}>
                      <td>
                        <strong>{agent.name}</strong>
                        <br />
                        <small className="muted">{agent.agent_id}</small>
                      </td>
                      <td className="status-cell">
                        <Badge value={agent.status} />
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </article>

        </aside>

        {/* Right: Containers & Jobs */}
        <section className="main-content">
          <article className="card">
            <h2>Running Containers</h2>
            <table className="table">
              <thead>
                <tr>
                  <th>Name</th>
                  <th>Image</th>
                  <th>Status</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {targets.length === 0 ? (
                  <tr>
                    <td colSpan={4} className="empty">
                      No running containers detected
                    </td>
                  </tr>
                ) : (
                  targets.map((target) => (
                    <tr key={target.id} className="clickable" onClick={() => selectTarget(target)} title="Click to dispatch">
                      <td>
                        <strong>{target.name}</strong>
                      </td>
                      <td className="muted monospace">{target.image}</td>
                      <td>
                        <Badge value={target.status} />
                      </td>
                      <td className="action-cell">→</td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </article>

          <article className="card">
            <h2>Recent Jobs</h2>
            <table className="table jobs-table">
              <thead>
                <tr>
                  <th>Image</th>
                  <th>Agent</th>
                  <th>Status</th>
                  <th>Created</th>
                </tr>
              </thead>
              <tbody>
                {sortedJobs.length === 0 ? (
                  <tr>
                    <td colSpan={4} className="empty">
                      No jobs yet
                    </td>
                  </tr>
                ) : (
                  sortedJobs.map((job) => (
                    <tr key={job.job_id} className="job-row">
                      <td>
                        <strong>{job.target_ref}</strong>
                      </td>
                      <td className="muted">{agentMap.get(job.target_agent_id) ?? job.target_agent_id}</td>
                      <td>
                        <Badge value={job.status} />
                      </td>
                      <td className="muted">{formatTime(job.created_at)}</td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </article>
        </section>
      </section>
        </>
      )}
    </main>
  );
}
