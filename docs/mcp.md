# MCP

Agents use `packages/mcp`. It calls the studio over HTTP and does not load a
model. Start the studio first with `bun start.ts`.

## Tools

| Tool | Section | What the agent gets back |
| --- | --- | --- |
| `design_voice` | Voice design | Design id and each candidate's duration, checks, and download url. Blocks until the candidates exist. |
| `lock_voice` | Voices | Confirms the new `voice_id`. |
| `list_voices` | Voices | Every locked voice. |
| `speak` | Speech | Absolute path of the WAV, plus duration and quality checks. Blocks until the file is on disk. |

`speak` writes `data/out/<voice_id>-<speech_id>.wav`, or `VOICE_GENERATOR_OUT`
when that is set. The agent passes that path to whatever consumes the audio.

## Install

```bash
bun install --cwd packages/mcp
```

Cursor in this repository reads `.cursor/mcp.json`. Anywhere else, copy
`mcp.json.example` into the client config. Set `VOICE_GENERATOR_URL` when the
studio is not on `http://127.0.0.1:8180`, and `VOICE_GENERATOR_TOKEN` when the
studio requires one.

```json
{
  "mcpServers": {
    "voice-generator": {
      "command": "bun",
      "args": ["packages/mcp/src/index.ts"],
      "env": {
        "VOICE_GENERATOR_URL": "http://127.0.0.1:8180",
        "VOICE_GENERATOR_OUT": "data/out"
      }
    }
  }
}
```

Run the command from the repository root so `packages/mcp/src/index.ts` resolves.
