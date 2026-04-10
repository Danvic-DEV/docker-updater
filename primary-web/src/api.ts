import type { Agent, AgentBootstrapCommandResponse, DockerTarget, Job } from "./types";

// In development: the browser proxies through Vite (localhost:5173/admin-api -> localhost:8001)
// In production: the browser can reach localhost:8001 directly (same container)
const ADMIN_API_BASE_URL = import.meta.env.DEV ? "/admin-api" : "http://localhost:8001";

async function parseJson<T>(response: Response): Promise<T> {
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `Request failed with status ${response.status}`);
  }
  return (await response.json()) as T;
}

export async function fetchAgents(): Promise<Agent[]> {
  return parseJson<Agent[]>(await fetch(`${ADMIN_API_BASE_URL}/api/agents`));
}

export async function fetchJobs(): Promise<Job[]> {
  return parseJson<Job[]>(await fetch(`${ADMIN_API_BASE_URL}/api/jobs`));
}

export async function fetchDockerTargets(): Promise<DockerTarget[]> {
  return parseJson<DockerTarget[]>(await fetch(`${ADMIN_API_BASE_URL}/api/docker/targets`));
}

export async function createJob(input: { target_ref: string; source_type: string; target_agent_id: string }): Promise<Job> {
  return parseJson<Job>(
    await fetch(`${ADMIN_API_BASE_URL}/api/jobs`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(input),
    })
  );
}

export async function createAgentBootstrapCommand(input: {
  agent_id: string;
  agent_name: string;
  primary_api_base_url?: string;
  agent_image?: string;
}): Promise<AgentBootstrapCommandResponse> {
  return parseJson<AgentBootstrapCommandResponse>(
    await fetch(`${ADMIN_API_BASE_URL}/api/agents/bootstrap-command`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(input),
    })
  );
}
