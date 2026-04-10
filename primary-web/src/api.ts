import type { Agent, DockerTarget, Job } from "./types";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

async function parseJson<T>(response: Response): Promise<T> {
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `Request failed with status ${response.status}`);
  }
  return (await response.json()) as T;
}

export async function fetchAgents(): Promise<Agent[]> {
  return parseJson<Agent[]>(await fetch(`${API_BASE_URL}/api/agents`));
}

export async function fetchJobs(): Promise<Job[]> {
  return parseJson<Job[]>(await fetch(`${API_BASE_URL}/api/jobs`));
}

export async function fetchDockerTargets(): Promise<DockerTarget[]> {
  return parseJson<DockerTarget[]>(await fetch(`${API_BASE_URL}/api/docker/targets`));
}

export async function createJob(input: { target_ref: string; source_type: string; target_agent_id: string }): Promise<Job> {
  return parseJson<Job>(
    await fetch(`${API_BASE_URL}/api/jobs`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(input),
    })
  );
}
