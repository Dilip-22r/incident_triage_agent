# Delta for hitl-approval

## ADDED Requirements

### Requirement: Sensitive actions require human approval
The agent MUST pause before executing any sensitive tool and MUST NOT execute it without an explicit approval for that thread.

#### Scenario: Escalation pauses
- GIVEN an incident where the model decides to call escalate_ticket
- WHEN the graph runs
- THEN execution stops before the sensitive_tools node
- AND no ticket is created

#### Scenario: Approved escalation executes
- GIVEN a thread paused before sensitive_tools
- WHEN an engineer approves
- THEN escalate_ticket runs once and the agent produces a final response

#### Scenario: Rejected escalation is not executed
- GIVEN a thread paused before sensitive_tools
- WHEN an engineer rejects with a reason
- THEN escalate_ticket is never executed
- AND the agent receives the rejection reason and continues reasoning

#### Scenario: Pause survives restart
- GIVEN a thread paused before sensitive_tools
- WHEN the process restarts
- THEN the thread is still awaiting approval
