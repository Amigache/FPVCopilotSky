# FPV Copilot Sky - Development Workflow

## Branch Strategy

This project follows a structured branching strategy with Phase-based development.

### Main Branch (`main`)

- Production-ready code
- All tests passing (238+ tests)
- Merged through Pull Requests
- Protected branch

### Feature Branches

Pattern: `feature/phase-<number>-<feature>`

Examples:

- `feature/phase-4-load-testing` - Load testing with JMeter
- `feature/phase-5-frontend-e2e` - Frontend E2E tests with Playwright
- `feature/phase-6-security-testing` - Security testing suite

### Workflow

1. **Create Feature Branch**

```bash
git checkout main
git pull origin main
git checkout -b feature/phase-<number>-<feature>
```

2. **Develop & Commit**

```bash
# Make changes
git add .
git commit -m "feat: add <feature>"
git push origin feature/phase-<number>-<feature>
```

3. **Create Pull Request**

- Go to GitHub
- Create PR from `feature/phase-<number>-<feature>` → `main`
- Add description of changes
- Wait for CI checks to pass

4. **Merge to Main**

```bash
# On GitHub, merge and delete branch
# Or locally:
git checkout main
git pull origin main
git merge --no-ff feature/phase-<number>-<feature>
git push origin main
```

## Phase Overview

| Phase | Status | Tests | Branch                            | Focus                      |
| ----- | ------ | ----- | --------------------------------- | -------------------------- |
| 1     | ✅     | -     | merged                            | CI/CD Pipeline             |
| 2     | ✅     | 100+  | `feature/enhance-testing-phase-2` | Unit & Integration Testing |
| 3     | ✅     | 138   | `main`                            | E2E Workflows & WebSocket  |
| 4     | 🔄     | -     | `feature/phase-4-*`               | Load Testing (next)        |

## Current Test Suite

```
Total Tests: 238+
├── Backend Tests: 28
├── Frontend Tests: 29
├── Integration Tests: 43
├── E2E Workflows: 66
├── WebSocket: 31
└── Video Pipeline: 41
```

## CI Checks

All PRs must pass:

1. ✅ CI Summary
2. ✅ Test React (Vitest)
3. ✅ Lint JavaScript (ESLint)
4. ✅ Lint Python (Black + Flake8)
5. ✅ Build Frontend (Vite)
6. ✅ Security Scan
7. ✅ CodeQL
8. ✅ GitHub Pages

## Code Quality Standards

- **Python**: Black (120 chars), Flake8, pytest
- **JavaScript**: ESLint (--max-warnings 0), Vitest
- **Tests**: Comprehensive with real-world scenarios
- **Documentation**: Phase completion summaries

## Running Tests Locally

```bash
# Backend tests
pytest tests/ -v

# Frontend tests
cd frontend/client && npm test

# With coverage
pytest tests/ --cov=app --cov-report=term-missing

# Specific test file
pytest tests/test_e2e_workflows.py -v

# Specific test class
pytest tests/test_e2e_workflows.py::TestCompleteSystemWorkflow -v
```

## Next Phases

### Phase 4: Load Testing

- Visual Studio Code snippets for quick testing
- JMeter load testing scripts
- API stress testing and benchmarking
- Concurrent user simulation

### Phase 5: Frontend E2E

- Playwright/Cypress browser automation
- User interaction testing
- Form validation scenarios
- Navigation and routing tests

### Phase 6: Security Testing

- Authentication testing
- API security validation
- Input validation and sanitization
- Penetration testing basics

## Quick Commands

```bash
# Check status
git status

# Sync with main
git fetch origin main
git rebase origin/main

# Create PR from command line (requires GitHub CLI)
gh pr create --title "Phase X: Description" --body "Details..."

# List all branches
git branch -a

# Delete local branch (after merge)
git branch -d feature/phase-X-name

# Delete remote branch
git push origin --delete feature/phase-X-name
```

## Contributing

1. Always work on feature branches
2. Keep commits focused and well-described
3. Run tests locally before pushing
4. Format code with Black/ESLint before committing
5. Write descriptive PR titles and descriptions
