import { Badge } from "./Badge";
import { statusColor } from "@/lib/utils";
import type { JobStatus } from "@/lib/api";

export function StatusBadge({ status }: { status: JobStatus }) {
  const labels: Record<JobStatus, string> = {
    pending: "Pending", running: "Running…", completed: "Completed",
    failed: "Failed", cancelled: "Cancelled",
  };
  return <Badge className={statusColor(status)}>{labels[status]}</Badge>;
}
