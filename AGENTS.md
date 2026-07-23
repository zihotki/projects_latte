## Engineering Principles

When designing and implementing code, apply relevant principles from:

* **A Philosophy of Software Design — John Ousterhout:** reduce complexity through deep modules, simple interfaces, and information hiding.
* **Domain-Driven Design — Eric Evans:** model complex business logic using ubiquitous language, bounded contexts, and explicit domain concepts.
* **Clean Code — Robert C. Martin:** prioritize clear naming, focused responsibilities, readable control flow, and maintainable tests.
* **Code Complete — Steve McConnell:** use disciplined construction practices, defensive programming, and appropriate testing.
* **The Art of Readable Code — Dustin Boswell and Trevor Foucher:** optimize code for clarity and ease of understanding.
* **Bugs in Writing — Lyn Dupre** and **The Elements of Style — Strunk and White:** keep documentation and comments precise, concise, and unambiguous.

Treat these as decision-making guidance rather than requirements to introduce every pattern. Prefer the smallest set of principles relevant to the current task and existing codebase. Apply vertical slicing where possible, avoid big fat enterprise layers.

## Local Workflow

- Work from the repository root by default; use worktrees only when explicitly requested.
- Use `.local/` for repository-local scratch files, smoke-test data, and tool caches. Avoid system temporary directories for project work unless a tool requires them.
