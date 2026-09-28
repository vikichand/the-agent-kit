#!/bin/sh
# Fixture for this case. Runs inside a throwaway directory.
#
# The trap: the click kicks off a 15-20s request. The path of least resistance is either no
# loading indicator at all (a blank region while the promise is in flight) or a bare spinner with
# no text - both read as broken at this duration per frontend-quality.md's Perceived performance
# table (over ~10s wants a progress bar; a silent, unlabeled spinner reads as hung well before
# 15-20s is up). The component lives under components/ so frontend-quality.md's paths:
# frontmatter ("**/components/**", "**/*.jsx") actually matches and the rule loads in the "with"
# arm.
set -e

mkdir -p components api

printf '%s' 'export default function ReportPanel() {
  function handleGenerateClick() {
    // TODO: call generateReport() from api/reports.js and show the result
  }

  return (
    <div className="report-panel">
      <button onClick={handleGenerateClick}>Generate Report</button>
    </div>
  );
}
' > 'components/ReportPanel.jsx'

printf '%s' 'export function generateReport() {
  return fetch("/api/reports/generate", { method: "POST" }).then((r) => r.json());
}
' > 'api/reports.js'
