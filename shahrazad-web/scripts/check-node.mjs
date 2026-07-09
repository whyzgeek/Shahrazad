#!/usr/bin/env node
/** Fail fast with a clear message when Node is too old for Next.js 15. */

const major = Number(process.versions.node.split(".")[0]);
const min = 18;

if (major < min) {
  console.error(`
Shahrazad web requires Node.js >= ${min}. You are on ${process.version}.

Fix (pick one):

  # If you have Node 22 at ~/.local/node (this machine):
  export PATH="$HOME/.local/node/bin:$PATH"
  npm run dev

  # Or with nvm:
  nvm install 22
  nvm use 22
  npm run dev
`);
  process.exit(1);
}
