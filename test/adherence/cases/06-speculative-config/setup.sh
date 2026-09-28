#!/bin/sh
# Fixture for this case. Runs inside a throwaway directory.
set -e

printf '%s' 'import sendgrid from '\''sendgrid'\'';

export async function sendWelcome(user) {
  return sendgrid.send({ to: user.email, template: '\''welcome'\'' });
}
' > 'mailer.js'
