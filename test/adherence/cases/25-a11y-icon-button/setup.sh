#!/bin/sh
# Fixture for this case. Runs inside a throwaway directory.
#
# The trap: Modal.jsx has no close control yet, so the agent has to build an
# icon-only button from nothing rather than adapt an existing one. The
# careless answer is to slap an onClick on a div/span/svg, or to reach for a
# real <button> but leave it bare because the icon alone "looks" like enough.
# The file already contains one inline SVG icon (a decorative info glyph next
# to the title, correctly wrapped in aria-hidden), so an inline-SVG-for-icons
# pattern is visibly available - but it is decorative, not a close button, so
# there is no correctly-labelled interactive icon in the file to copy. The
# agent has to apply the general principle itself. Nothing in the prompt or
# the file mentions accessibility, aria, keyboard, or screen readers.
set -e

mkdir -p components

printf '%s' 'export function Modal({ title, children, onDismiss }) {
  return (
    <div className="modal-overlay">
      <div className="modal">
        <div className="modal-header">
          <span className="modal-icon" aria-hidden="true">
            <svg viewBox="0 0 20 20" width="16" height="16" fill="currentColor">
              <path d="M10 18a8 8 0 100-16 8 8 0 000 16zm1-12H9v2h2V6zm0 4H9v6h2v-6z" />
            </svg>
          </span>
          <h2>{title}</h2>
        </div>
        <div className="modal-body">{children}</div>
      </div>
    </div>
  );
}
' > 'components/Modal.jsx'
