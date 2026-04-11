export type Agent = {
  agent_id: string;
  name: string;
  status: "online" | "offline";
  last_heartbeat: string;
};

export type Job = {
  job_id: string;
  target_ref: string;
  target_container_name?: string;
  source_type: string;
  target_agent_id: string;
  status: "queued" | "in_progress" | "completed" | "failed" | "rolled_back";
  created_at: string;
  updated_at: string;
  logs: string[];
};

export type DockerTarget = {
  id: string;
  name: string;
  image: string;
  status: string;
  has_update: boolean;
  update_check_status?: "available" | "up_to_date" | "unknown";
  update_check_error?: string | null;
  agent_id?: string;
};
