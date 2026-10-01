#!/usr/bin/env bun
// voice-design is served by the studio at /mcp. There is no local command.
const host = process.env.HOST ?? "127.0.0.1";
const port = process.env.PORT ?? "8180";
const shown = host === "0.0.0.0" || host === "::" ? "127.0.0.1" : host;
console.log(`voice-design is http://${shown}:${port}/mcp`);
console.log("Start it with bun start.ts from the voice-design folder.");
