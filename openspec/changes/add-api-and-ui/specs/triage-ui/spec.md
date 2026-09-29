# Delta for triage-ui

## ADDED Requirements

### Requirement: Gradio UI for incident triage
The UI SHALL provide Thread ID input, Incident Description input, Trigger Triage button, Approve Escalation button, Reject Action button, Rejection Reason field, Workflow State label, and Agent Log output.

#### Scenario: Triage triggered with valid thread
- GIVEN a valid thread ID and message
- WHEN Trigger Triage is clicked
- THEN the Agent Log shows the triage result and Workflow State updates

#### Scenario: Approve with empty Thread ID is rejected
- GIVEN Thread ID is empty
- WHEN Approve Escalation is clicked
- THEN an error message is shown

### Requirement: Shared service layer
The REST handlers and the Gradio callbacks MUST share one service layer with no duplicated approve/reject logic.

#### Scenario: Approval from REST and UI produce identical results
- GIVEN a paused thread
- WHEN approval is sent via REST or UI
- THEN both call the same _approve() function
