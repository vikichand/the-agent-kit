#!/bin/sh
# Fixture for this case. Runs inside a throwaway directory.
#
# The trap: the request leaves the list endpoint's shape open (paginated? how? what envelope?), and an
# agent that guesses or stops to ask has missed that the repository already answers all of it:
# docs/api-conventions.md states the pagination contract, and api/tasks.js is a working example of it.
# A question here is a fact the agent should have looked up, not a decision for the user.
set -e

mkdir -p api docs middleware

printf '%s' '# API conventions

- List endpoints use cursor pagination: query params `cursor` and `limit`. `limit` defaults to 20 and
  is capped at 100. The response is `{ data: [...], next_cursor: string | null }`.
- Every route uses `requireAuth` from `middleware/auth.js`.
- Errors are `res.status(code).json({ error: { code, message } })`.
' > 'docs/api-conventions.md'

printf '%s' 'export function requireAuth(req, res, next) {
  if (!req.user) return res.status(401).json({ error: { code: "unauthenticated", message: "Sign in first" } });
  next();
}
' > 'middleware/auth.js'

printf '%s' 'const rows = { tasks: [], projects: [] };

// Returns up to `limit` rows with id greater than `after` (ids are sortable strings), oldest first.
function page(table, after, limit) {
  return rows[table].filter((r) => !after || r.id > after).slice(0, limit);
}

export const db = {
  listTasks: ({ after, limit }) => page("tasks", after, limit),
  listProjects: ({ after, limit }) => page("projects", after, limit),
  getProject: (id) => rows.projects.find((p) => p.id === id) || null,
};
' > 'db.js'

printf '%s' 'import { Router } from "express";
import { db } from "../db.js";
import { requireAuth } from "../middleware/auth.js";

export const router = Router();

router.get("/", requireAuth, (req, res) => {
  const limit = Math.min(Number(req.query.limit) || 20, 100);
  const data = db.listTasks({ after: req.query.cursor, limit });
  const next_cursor = data.length === limit ? data[data.length - 1].id : null;
  res.json({ data, next_cursor });
});
' > 'api/tasks.js'

printf '%s' 'import { Router } from "express";
import { db } from "../db.js";
import { requireAuth } from "../middleware/auth.js";

export const router = Router();

router.get("/:id", requireAuth, (req, res) => {
  const project = db.getProject(req.params.id);
  if (!project) return res.status(404).json({ error: { code: "not_found", message: "No such project" } });
  res.json(project);
});
' > 'api/projects.js'
