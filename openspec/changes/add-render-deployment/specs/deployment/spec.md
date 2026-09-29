# Delta for deployment

## ADDED Requirements

### Requirement: Port binding
The service SHALL bind to the port provided in the $PORT environment variable.

#### Scenario: Starts on dynamic port
- GIVEN PORT=8080 is set
- WHEN the app starts
- THEN it listens on 0.0.0.0:8080

### Requirement: Secrets from environment only
Secrets SHALL come only from environment variables. .env SHALL NOT be committed.

#### Scenario: .env not tracked
- GIVEN the project is cloned fresh
- WHEN git ls-files is run
- THEN .env does not appear in the output

### Requirement: Health check endpoint
GET /healthz SHALL return 200 without calling Gemini or the database.

#### Scenario: Health check is lightweight
- GIVEN the app is running
- WHEN GET /healthz is called
- THEN HTTP 200 {"status": "ok"} is returned with no external calls

### Requirement: Cold-start state recovery
A paused approval SHALL still be resumable after a cold start.

#### Scenario: Approval survives restart
- GIVEN a thread paused before sensitive_tools
- WHEN the process restarts and POST /approve is called
- THEN the thread resumes and returns RESOLVED
