# Repository Instructions

## Commit Messages

Use Conventional Commits for every commit message.

Format:

```text
type(scope): summary
```

The scope is optional when it does not add clarity:

```text
type: summary
```

Common types:

- `feat`: user-facing feature or behavior change
- `fix`: bug fix
- `docs`: documentation-only change
- `test`: test-only change
- `refactor`: code change that does not alter behavior
- `chore`: maintenance, tooling, or repository housekeeping

Examples:

```text
feat: support Discord apps in user Applications
docs: document supported Discord install locations
chore: add repository agent instructions
```

Keep the summary imperative, lowercase after the type, and under 72 characters
when practical.
