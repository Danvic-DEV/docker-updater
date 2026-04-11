import { useEffect, useMemo, useState } from "react";
import type { FormEvent } from "react";

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
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [lastUpdatedAt, setLastUpdatedAt] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [updateModal, setUpdateModal] = useState<{ target: DockerTarget; agentId: string } | null>(null);

  const agentMap = useMemo(() => new Map(agents.map((a) => [a.agent_id, a.name])), [agents]);
  const sortedJobs = useMemo(() => [...jobs].sort((a, b) => b.created_at.localeCompare(a.created_at)), [jobs]);

  async function refresh(showIndicator = false) {
    if (showIndicator) {
      setIsRefreshing(true);
    }
    try {
      const [nextAgents, nextJobs, nextTargets] = await Promise.all([fetchAgents(), fetchJobs(), fetchDockerTargets()]);
      setAgents(nextAgents);
      setJobs(nextJobs);
      setTargets(nextTargets);
      setLastUpdatedAt(new Date().toLocaleTimeString());
      setError(null);

      if (updateModal && !updateModal.agentId && nextAgents[0]) {
        setUpdateModal((current) => ({ ...current!, agentId: nextAgents[0].agent_id }));
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unknown error");
    } finally {
      if (showIndicator) {
        setIsRefreshing(false);
      }
    }
  }

  async function onSubmitUpdate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!updateModal?.target || !updateModal?.agentId) return;

    try {
      await createJob({
        target_ref: updateModal.target.image,
        target_container_name: updateModal.target.name,
        source_type: "registry",
        target_agent_id: updateModal.agentId,
      });
      setUpdateModal(null);
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create job");
    }
  }

  useEffect(() => {
    refresh();
    const id = window.setInterval(() => refresh(), 5000);
    return () => window.clearInterval(id);
  }, []);

  function openUpdateModal(target: DockerTarget) {
    const defaultAgentId = target.agent_id || (agents.length > 0 ? agents[0].agent_id : "");
    setUpdateModal({ target, agentId: defaultAgentId });
  }

  const agentsOnline = agents.filter((a) => a.status === "online").length;
  const agentsOffline = agents.filter((a) => a.status === "offline").length;
  const jobsComplete = jobs.filter((j) => j.status === "completed").length;
  const jobsFailed = jobs.filter((j) => j.status === "failed").length;
  const jobsInProgress = jobs.filter((j) => j.status === "in_progress").length;

  return (
    <main className="layout">
      <header className="header">
        <h1>Docker Updater</h1>
        <div className="header-actions">
          <button onClick={() => refresh(true)} title="Refresh" disabled={isRefreshing}>
            {isRefreshing ? '…' : '↻'}
          </button>
        </div>
      </header>

      <section className="muted" style={{ marginTop: "-0.5rem", marginBottom: "0.5rem" }}>
        Last updated: {lastUpdatedAt ?? "pending..."}
      </section>

      {error ? <section className="error">{error}</section> : null}

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
        {/* Left: Agents */}
        <aside className="sidebar">

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
                  <th>Agent</th>
                  <th>Image</th>
                  <th>Status</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {targets.length === 0 ? (
                  <tr>
                    <td colSpan={5} className="empty">
                      No running containers detected
                    </td>
                  </tr>
                ) : (
                  targets.map((target) => (
                    <tr key={target.id}>
                      <td>
                        <strong>{target.name}</strong>
                        {target.has_update && <span className="update-badge">UPDATE</span>}
                      </td>
                      <td className="muted monospace">{target.image}</td>
                      <td className="muted">{agentMap.get(target.agent_id ?? "") ?? target.agent_id ?? "-"}</td>
                      <td>
                        <Badge value={target.status} />
                      </td>
                      <td className="action-cell">
                        <button 
                          className={`action-btn ${target.has_update ? 'has-update' : ''}`}
                          onClick={() => openUpdateModal(target)} 
                          title={target.has_update ? "Update available - click to update" : "Pull latest image"}
                        >
                          ↗
                        </button>
                      </td>
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

      {/* Update Modal */}
      {updateModal && (
        <div className="modal-overlay" onClick={() => setUpdateModal(null)}>
          <div className="modal-box" onClick={(e) => e.stopPropagation()}>
            <h3>Update {updateModal.target.name}</h3>
            <p className="muted">{updateModal.target.image}</p>
            <form onSubmit={onSubmitUpdate} className="form">
              <label>
                Select Agent
                <select
                  value={updateModal.agentId}
                  onChange={(e) =>
                    setUpdateModal((current) => ({ ...current!, agentId: e.target.value }))
                  }
                >
                  {agents.map((agent) => (
                    <option key={agent.agent_id} value={agent.agent_id}>
                      {agent.name} — {agent.status}
                    </option>
                  ))}
                </select>
              </label>
              <div className="modal-actions">
                <button type="button" onClick={() => setUpdateModal(null)} className="btn-secondary">
                  Cancel
                </button>
                <button type="submit">Run Update</button>
              </div>
            </form>
          </div>
        </div>
      )}
      </>
    </main>
  );
}
