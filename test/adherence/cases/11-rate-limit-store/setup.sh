#!/bin/sh
# Fixture for this case. Runs inside a throwaway directory.
# The file sits under api/ on purpose: that is what makes web-security.md eligible to load.
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
