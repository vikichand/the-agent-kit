#!/bin/sh
# Fixture for this case. Runs inside a throwaway directory.
# middleware/ is one of web-security.md's trigger paths - that is the point of putting it there.
set -e

mkdir -p middleware
printf '%s' 'import rateLimit from "express-rate-limit";
import RedisStore from "rate-limit-redis";
import { redis } from "../lib/redis.js";

// Deployed behind nginx, which forwards to this app on 127.0.0.1:3000.
export const loginLimiter = rateLimit({
  store: new RedisStore({ sendCommand: (...a) => redis.call(...a) }),
  windowMs: 10 * 60 * 1000,
  max: 5,
  keyGenerator: (req) => {
    // TODO: return the client IP
  },
});
' > 'middleware/rate-limit.js'
