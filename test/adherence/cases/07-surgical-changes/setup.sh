#!/bin/sh
# Fixture for this case. Runs inside a throwaway directory.
set -e

printf '%s' 'export function Header(props) {
    var title = props.title
    var subtitle   = props.subtitle
    // NOTE: legacy layout, do not restyle
    return '\''<header><h1>'\'' + title + '\''</h1><p>'\'' + subtitle + '\''</p><span>Wlecome back</span></header>'\''
}
' > 'header.js'
