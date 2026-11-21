# Review subagents

Read the diff, related code, and contract. Identify concrete issues and report them to the main agent. Run checks locally when the session permits. Leave edits, commits, PRs, and cluster operations to the main agent.

## forecast-reviewer

- Verify monetary units, the 14 forecast dates, same-day transaction totals, and how the first shortfall is identified.
- Confirm that rescheduling a positive payment only changes the alternative forecast. Check invalid CSV, duplicate IDs, and moves outside the forecast window.
- The example in `demo/` should show Friday balances of −5,000 EUR and +4,000 EUR.
- Identify the tests that support each finding and any edge cases that remain untested.

## integration-reviewer

- Compare actual requests and responses against `contracts/openapi.json`. Review how the interface handles HTTP 422 and model outages reported as HTTP 503.
- Check the ports and names of the Service, Route, and Deployment. Verify that model settings are passed correctly and that the token stays out of the repository and logs.
- Confirm that the demo screenshot and URL in the report match the version under review. Verify live model use against the actual test results.
- Record what the team needs to check at the deployed URL before the demo.

## Report format

List blocking issues first. For each finding, give the file and line, the user impact, and steps to reproduce. End with the checks you ran and the checks that required access you did not have.
