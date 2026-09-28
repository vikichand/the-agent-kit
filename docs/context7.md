<!-- Optional. Drop this into ~/.claude/rules/ (machine-wide) or a project's PROJECT-CONFIG block
     when the Context7 MCP server is installed. It is the enforcement half of the kit's "verify API and
     configuration facts against the version in use" rule (AGENTS.md section 5): the rule states the principle, this makes it a
     procedure the agent actually follows. Useless without the server - install that first
     (docs/environment-setup-prompt.md, Step 2a). -->

# Context7 - route library questions to live docs

Use Context7 MCP to fetch current documentation for a library, framework, SDK, API, CLI tool, or
cloud service when the fact is unfamiliar, uncertain, or version-sensitive: API syntax you have not
seen used correctly in this repo, configuration keys, version migration, library-specific debugging,
setup instructions, CLI usage. The repo's own verified usage of the same API and version is a source;
reuse it rather than fetching again. Prefer Context7 over web search for library docs.

Do not use for: refactoring, writing scripts from scratch, debugging business logic, code review, or
general programming concepts.

## Steps

1. Start with `resolve-library-id` using the library name and the user's question, unless the user
   provides an exact library ID in `/org/project` format or you already resolved it this session
2. Pick the best match (ID format: `/org/project`) by: exact name match, description relevance, code
   snippet count, source reputation (High/Medium preferred), and benchmark score (higher is better).
   If results don't look right, try alternate names or queries (e.g., "next.js" not "nextjs", or
   rephrase the question). Use version-specific IDs when the user mentions a version
3. `query-docs` with the selected library ID and the user's full question (not single words)
4. Answer using the fetched docs
