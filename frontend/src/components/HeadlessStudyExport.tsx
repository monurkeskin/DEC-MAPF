import { saveJson } from "../artifacts";
import { portableStudy } from "../study";
import type { JobSubmissionRequest } from "../api/types";
export function HeadlessStudyExport({
  portableInput,
}: {
  portableInput: JobSubmissionRequest;
}) {
  return (
    <details>
      <summary>Run these inputs without the GUI</summary>
      <p>
        The exported scenario is self-contained. Planning on your machine
        records its own source identity. The study has one trial and a separate
        finite batch budget.
      </p>
      <button
        onClick={() => saveJson("study.json", portableStudy(portableInput))}
      >
        Download headless study
      </button>
      <pre tabIndex={0}>
        mapf batch plan study.json --output manifest.json{"\n"}mapf batch run
        manifest.json --workspace runs/my-study
      </pre>
    </details>
  );
}
