#!/bin/sh
# Fixture for this case. Runs inside a throwaway directory.
set -e

printf '%s' 'export const add = (a, b) => a - b;   // bug: should add
' > 'math.js'
git init -q
git config user.email t@e.com
git config user.name T
git add -A
git -c core.autocrlf=false commit -qm 'initial'
