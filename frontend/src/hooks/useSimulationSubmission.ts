import { useRef, useState } from "react";
import { post, submitSimulationJob } from "../api/client";
import type {
  JobStatusResponse,
  JobSubmissionRequest,
  Plan,
} from "../api/types";

type Options = {
  plan: Plan | null;
  input: () => JobSubmissionRequest;
  onPreview: (plan: Plan) => void;
  onStarted: (job: JobStatusResponse) => Promise<void>;
  reportError: (error: unknown) => void;
  setError: (message: string) => void;
};

export function useSimulationSubmission({
  plan,
  input,
  onPreview,
  onStarted,
  reportError,
  setError,
}: Options) {
  const [submitting, setSubmitting] = useState(false);
  const submitKey = useRef<string | null>(null);
  const preview = async () => {
    setError("");
    submitKey.current = null;
    try {
      onPreview(await post<Plan>("/plans/preview", { jobs: [input()] }));
    } catch (error) {
      reportError(error);
    }
  };
  const start = async () => {
    if (!plan || submitting) return;
    setSubmitting(true);
    setError("");
    submitKey.current ??= crypto.randomUUID();
    try {
      await onStarted(await submitSimulationJob(input(), submitKey.current));
    } catch (error) {
      reportError(error);
    } finally {
      setSubmitting(false);
    }
  };
  return { submitting, preview, start };
}
