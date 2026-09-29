# Delta for triage-api

## ADDED Requirements

### Requirement: POST /chat endpoint
The API SHALL accept {thread_id, message} and return COMPLETED or AWAITING_APPROVAL with pending action details.

#### Scenario: Triage completes without escalation
- GIVEN a message that does not require escalation
- WHEN POST /chat is called
- THEN status is COMPLETED and message contains the triage summary

#### Scenario: Triage awaits approval
- GIVEN a message that triggers escalate_ticket
- WHEN POST /chat is called
- THEN status is AWAITING_APPROVAL and pending_action is "escalate_ticket"

### Requirement: POST /approve endpoint
The API SHALL accept {thread_id, approved, rejection_reason?} and return RESOLVED, REJECTED_AND_RESUMED, or HTTP 400 when nothing is pending.

#### Scenario: Approve resolves the thread
- GIVEN a thread awaiting approval
- WHEN POST /approve with approved=true
- THEN status is RESOLVED

#### Scenario: Reject resumes the thread
- GIVEN a thread awaiting approval
- WHEN POST /approve with approved=false
- THEN status is REJECTED_AND_RESUMED

#### Scenario: 400 when nothing pending
- GIVEN a thread with no pending approval
- WHEN POST /approve is called
- THEN HTTP 400 is returned
