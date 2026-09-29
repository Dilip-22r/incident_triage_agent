# Delta for triage-agent

## ADDED Requirements

### Requirement: Health-first investigation
The agent SHALL call query_service_health before searching runbooks for every incident.

#### Scenario: Health checked before runbooks
- GIVEN an incident message is submitted
- WHEN the agent processes it
- THEN query_service_health is called before search_remediation_runbooks

### Requirement: Runbook retrieval
The agent SHALL return the top 2 runbooks matching the incident, or "No relevant runbooks found." if none match.

#### Scenario: Returns top 2 matches
- GIVEN 3 runbooks in the knowledge base
- WHEN search_remediation_runbooks is called
- THEN at most 2 results are returned ordered by similarity

### Requirement: Unknown service handling
query_service_health called with an unknown service name SHALL return a not-found message rather than raising an exception.

#### Scenario: Unknown service
- GIVEN a service name not in the health table
- WHEN query_service_health is called with that name
- THEN a descriptive not-found string is returned

### Requirement: State persistence
Given a thread_id, a new process SHALL be able to load the same conversation state.

#### Scenario: State survives process restart
- GIVEN a completed triage with thread_id "test-123"
- WHEN a new process loads state for thread_id "test-123"
- THEN the same messages are present

### Requirement: Content normalisation
List-structured model output SHALL be flattened to plain text by extract_text.

#### Scenario: List content is flattened
- GIVEN a model response with content [{"text": "foo"}, "bar"]
- WHEN extract_text is called
- THEN the result is "foo bar"
