# Review subagents

Read the diff, related code, and contract. Identify concrete issues and report them to the main agent. Run checks locally when the session permits. Leave edits, commits, PRs, and cluster operations to the main agent.

## forecast-reviewer

- Verify monetary units (integer minor units across `EUR`, `PLN`, `USD`, `CHF`, `GBP`), the 14 forecast dates, same-day transaction totals, and how the first and deepest shortfalls are identified.
- Confirm that rescheduling a positive or negative payment only changes the alternative forecast, and that `classify_transaction()` never tags walk-in card customers (`retail_non_contactable`) or mandatory taxes/social/staff payroll (`fixed_mandatory`) as actionable email targets.
- Check invalid CSV handling (HTTP 422), duplicate IDs, moves outside the forecast window, and canonical fixtures in `demo/qa_cases.json` (`amalfi_sample`, `credit_peak`, `no_shortfall`).
- Identify the tests that support each finding and any edge cases that remain untested.

## integration-reviewer

- Compare actual requests and responses against `contracts/openapi.json` (including `POST /api/action-plan`). Review how the interface handles HTTP 422 and model outages reported as HTTP 503.
- Check the ports and names of the Service, Route, and Deployment. Verify that `kernes-qwen-7b` (GPU primary) and `kernes-qwen` (CPU fallback) settings are passed correctly and that `CFO_MODEL_TOKEN` stays out of the repository and logs.
- Confirm that the demo screenshot and URL in the report match the version under review. Verify live model use against actual test results.
- Record what the team needs to check at the deployed URL before the demo.

## Report format

List blocking issues first. For each finding, give the file and line, the user impact, and steps to reproduce. End with the checks you ran and the checks that required access you did not have.
