# Delta for knowledge-base

## ADDED Requirements

### Requirement: Runbook storage
The system SHALL store runbooks in the `incident_docs` table with content, JSON metadata, and a 768-dimension embedding vector.

#### Scenario: Schema matches embedding size
- GIVEN the migration has been applied
- WHEN a 768-dimension vector is inserted
- THEN the insert succeeds
- AND a vector of any other dimension is rejected

### Requirement: Idempotent seeding
Running the seed script more than once SHALL NOT create duplicate runbook rows.

#### Scenario: Re-running the seed
- GIVEN the three runbooks were already seeded
- WHEN seed_rag.py runs again
- THEN the table still contains exactly three runbook rows

### Requirement: Semantic retrieval function
The database SHALL expose `match_incident_docs(query_embedding, match_count, filter)` returning rows ordered by cosine similarity, filtered by metadata containment.

#### Scenario: Filter by service
- GIVEN runbooks for auth, database, and payments
- WHEN match_incident_docs is called with filter {"service": "auth"}
- THEN only auth runbooks are returned
