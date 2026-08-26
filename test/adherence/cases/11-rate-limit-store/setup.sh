#!/bin/sh
# Fixture for this case. Runs inside a throwaway directory.
#
# Two things are deliberate. api/ is one of web-security.md's trigger paths, so the rule is
# eligible to load. And the fact that decides the answer - this runs as four replicas, so an
# in-process counter gives each replica its own budget - is in the compose file, NOT in the
# prompt. Telling the agent "you run four instances" is handing it the answer; a real repo
# never does that, it just has the file sitting there. The case is whether the agent looks.
set -e

mkdir -p api
printf '%s' 'import express from "express";

export const router = express.Router();

router.post("/login", async (req, res) => {
  // TODO: rate limiting goes here
  const { email, password } = req.body;
  const user = await verify(email, password);
  if (!user) return res.status(401).json({ error: "invalid credentials" });
  req.session.userId = user.id;
  res.json({ ok: true });
});
' > 'api/login.js'

printf '%s' 'services:
  api:
    build: .
    deploy:
      replicas: 4
    environment:
      - REDIS_URL=redis://cache:6379
    depends_on: [cache, db]
  cache:
    image: redis:7-alpine
  db:
    image: postgres:16-alpine
' > 'docker-compose.yml'
