# DevFlow AI

**AI-Powered Pull Request Review Platform**

DevFlow AI is an automated code review platform designed to analyze GitHub pull requests using a combination of static analysis and Large Language Models (LLMs). The platform is being built to identify potential bugs, security vulnerabilities, and code-quality issues while providing developers with structured, actionable feedback directly within their GitHub workflow.

The project focuses not only on AI-powered code analysis, but also on building a reliable event-driven backend capable of handling asynchronous jobs, duplicate webhook events, retries, failures, and concurrent review processing.

> **Project Status:** 🚧 Currently under active development.

---

## 🎯 Project Goals

DevFlow AI is being built to explore the intersection of **software engineering, distributed systems, and applied AI**.

The platform aims to:

* Automatically analyze GitHub pull requests.
* Detect potential correctness and security issues.
* Run static analysis using tools such as Ruff and Bandit.
* Use an LLM to perform contextual code review.
* Generate structured and actionable review findings.
* Publish review results through GitHub Check Runs.
* Process reviews asynchronously using background workers.
* Handle duplicate events and failed jobs safely.
* Measure review latency, throughput, AI quality, and system reliability.

---

## ⚙️ Planned Workflow

```text
Developer opens/updates Pull Request
                │
                ▼
         GitHub Webhook
                │
                ▼
        FastAPI Backend
                │
        ┌───────┴────────┐
        │                │
        ▼                ▼
   PostgreSQL       Redis Queue
                         │
                         ▼
                   Celery Worker
                         │
                ┌────────┴────────┐
                ▼                 ▼
          Static Analysis     AI Analysis
          Ruff + Bandit          LLM
                │                 │
                └────────┬────────┘
                         ▼
                  Report Aggregator
                         │
                  ┌──────┴──────┐
                  ▼             ▼
             PostgreSQL    GitHub Check Run
                  │
                  ▼
            React Dashboard
```

### Review Lifecycle

1. A developer opens or updates a pull request.
2. GitHub sends a signed webhook event to DevFlow AI.
3. The FastAPI backend validates the webhook and creates a review job.
4. The review job is persisted in PostgreSQL and submitted for asynchronous processing.
5. A Celery worker retrieves the pull-request changes.
6. Ruff and Bandit perform static analysis.
7. An LLM analyzes the changed code for additional issues.
8. Findings are validated, normalized, and deduplicated.
9. Results are stored in PostgreSQL.
10. DevFlow AI publishes the review through GitHub Checks.
11. Review history and metrics can be inspected through the dashboard.

---

## 🛠️ Tech Stack

### Backend

* Python
* FastAPI
* SQLAlchemy
* Alembic
* PostgreSQL

### Asynchronous Processing

* Redis
* Celery

### AI & Code Analysis

* LLM API
* Ruff
* Bandit
* Pydantic structured-output validation

### Frontend

* React
* TypeScript
* Vite

### Infrastructure

* Docker
* Docker Compose
* GitHub Actions

### Testing & Performance

* Pytest
* HTTPX
* Locust

### External Integration

* GitHub Apps
* GitHub REST API
* GitHub Webhooks
* GitHub Checks API

---

## 🔌 Planned API

| Method | Endpoint                   | Description                                |
| ------ | -------------------------- | ------------------------------------------ |
| `POST` | `/api/webhooks/github`     | Receive and validate GitHub webhook events |
| `GET`  | `/api/repositories`        | List connected repositories                |
| `GET`  | `/api/reviews`             | List pull-request reviews                  |
| `GET`  | `/api/reviews/{id}`        | Retrieve a review and its findings         |
| `GET`  | `/api/reviews/{id}/status` | Retrieve review-processing status          |
| `POST` | `/api/reviews/{id}/retry`  | Retry an eligible failed review            |
| `GET`  | `/api/metrics/summary`     | Retrieve processing metrics                |
| `GET`  | `/health`                  | Service health check                       |

---

## 🤖 AI Review Pipeline

The AI reviewer is designed around structured and verifiable outputs rather than unrestricted natural-language responses.

```text
Pull Request Diff
        │
        ▼
Input Preparation
        │
        ├── Diff size limits
        ├── File filtering
        └── Secret redaction
        │
        ▼
Static Analysis
Ruff + Bandit
        │
        ▼
LLM Code Analysis
        │
        ▼
Pydantic Validation
        │
        ├── Validate file paths
        ├── Validate line numbers
        └── Validate response schema
        │
        ▼
Finding Normalization
        │
        ▼
Deduplication
        │
        ▼
Final Review Report
```

Repository content is treated as **untrusted input**. AI-generated output will be validated before findings can be published.

The LLM is used as an advisory reviewer and is not permitted to execute commands, access application secrets, modify repositories, or automatically merge pull requests.

---

## 🔒 Reliability & Security

DevFlow AI is being designed around several important reliability principles.

### Idempotent Processing

GitHub may deliver the same webhook multiple times. Review jobs will use a unique identity based on:

```text
repository + pull request number + head commit SHA
```

This prevents duplicate logical reviews for the same commit.

### Commit-Aware Reviews

Every review is associated with an exact Git commit SHA.

Before publishing findings, DevFlow AI will verify that the pull request still references that commit. Reviews for outdated commits can therefore be marked as superseded instead of being presented as current results.

### Failure Recovery

Background jobs will support:

* bounded retries
* exponential backoff
* terminal failure states
* stale-job detection
* worker failure recovery

PostgreSQL acts as the durable source of review-job state instead of relying solely on the Redis queue.

### Secure Code Analysis

The initial version will **not execute arbitrary repository code or install repository dependencies**.

Static analysis will operate on retrieved source files without running untrusted project scripts.

---

## 🧪 Testing Strategy

The project will include several levels of testing:

### Unit Tests

Testing individual components such as:

* webhook signature validation
* job creation
* duplicate detection
* job state transitions
* AI response parsing
* finding validation
* retry logic

### Integration Tests

Testing interactions between:

```text
FastAPI ↔ PostgreSQL ↔ Redis ↔ Celery
```

### Reliability Tests

Failure scenarios will include:

* duplicate GitHub webhook deliveries
* concurrent workers
* worker crashes
* Redis interruptions
* malformed LLM responses
* GitHub API rate limiting
* stale pull-request commits

### AI Evaluation

A labeled dataset of Python code changes will be used to evaluate AI review quality using:

* Precision
* Recall
* False-positive rate

The LLM-based reviewer will also be compared with static analysis alone.

---

## 📊 Performance Goals

The following values are **development targets and not measured results**:

| Metric                    |    Initial Target |
| ------------------------- | ----------------: |
| Webhook API P95 latency   |        `< 500 ms` |
| Load-test queue           | `100 review jobs` |
| Duplicate logical reviews |               `0` |
| AI evaluation dataset     |    `50+ examples` |
| Backend test coverage     |            `80%+` |

Actual benchmark results will be documented after implementation and reproducible testing.

---

## 🗺️ Development Roadmap

### Phase 1 — Backend & GitHub Integration

* [ ] Initialize FastAPI backend
* [ ] Configure PostgreSQL
* [ ] Configure Redis
* [ ] Add SQLAlchemy models
* [ ] Add Alembic migrations
* [ ] Create GitHub App
* [ ] Verify webhook signatures
* [ ] Implement review-job creation
* [ ] Add Celery workers
* [ ] Retrieve pull-request diffs
* [ ] Integrate Ruff and Bandit

### Phase 2 — AI Review Engine

* [ ] Integrate LLM provider
* [ ] Implement structured review prompts
* [ ] Validate responses with Pydantic
* [ ] Validate file and line references
* [ ] Normalize findings
* [ ] Deduplicate findings
* [ ] Publish GitHub Check Runs
* [ ] Build React dashboard

### Phase 3 — Reliability & Evaluation

* [ ] Implement retry and recovery mechanisms
* [ ] Add unit tests
* [ ] Add integration tests
* [ ] Add reliability tests
* [ ] Build AI evaluation dataset
* [ ] Benchmark AI review quality
* [ ] Run load tests
* [ ] Add CI/CD
* [ ] Deploy application
* [ ] Document benchmark results

---

## 🚧 Current Status

DevFlow AI is currently under development.

The first milestone is building the core infrastructure:

```text
GitHub Webhook
      ↓
FastAPI
      ↓
PostgreSQL
      ↓
Redis / Celery
      ↓
Review Worker
```

AI review and GitHub Check integration will be added after the core review pipeline is reliable.

---

## 📈 Future Improvements

Potential future extensions include:

* JavaScript and TypeScript repository support
* Java repository support
* repository-specific review policies
* multi-provider LLM support
* retrieval of additional repository context
* developer feedback loops for AI findings
* calibrated finding confidence
* advanced observability and tracing
* isolated sandbox environments for automated test execution

---


## ⚠️ Disclaimer

DevFlow AI is an experimental developer tool. AI-generated code-review findings may contain false positives or miss issues and should not replace human code review or established security practices.
