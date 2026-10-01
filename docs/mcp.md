# MCP

Agents call voice-design at `http://<server>:8180/mcp`. The studio serves that
endpoint. It calls the engine on this machine and does not load a model.
Start the stack with `bun start.ts`.

## Tools

| Tool | Section | What the agent gets back |
| --- | --- | --- |
| `design_voice` | Voice design | Design id and each candidate WAV's absolute path, duration, and checks. Blocks until the files are on disk. |
| `list_designs`, `get_design` | Voice design | Recent designs, or one design's checks and urls. |
| `preview_voice` | Voice design | Absolute paths for one candidate or every candidate of an existing design. |
| `lock_voice` | Voices | Confirms the new `voice_id`. |
| `list_voices`, `get_voice`, `delete_voice` | Voices | The locked library, one voice, or a deletion. |
| `download_voice` | Voices | Absolute path of `master.wav`, `preview.txt`, `instruct.txt`, or `voice.json`. |
| `speak` | Speech | Absolute path of the WAV, plus duration and quality checks. Blocks until the file is on disk. |
| `list_speech`, `get_speech`, `download_speech` | Speech | Recent takes, one take, or a saved WAV for a finished take. |
| `list_templates`, `get_template`, `save_template`, `update_template`, `duplicate_template`, `delete_template` | Templates | Voice recipes for later designs. Built-in templates stay as shipped. |
| `preview_template`, `set_template_sample` | Templates | The sample clip's path, or a new sample taken from a design candidate. |
| `list_profile`, `save_profile_voice`, `remove_profile_voice` | Profile | Voices kept for reuse. Removing one from the profile leaves the locked voice in place. |
| `list_jobs`, `get_job`, `cancel_job`, `delete_job` | Jobs | The shared queue. Cancel applies to a queued job. Delete removes a job and its stored audio. |

`design_voice` and `preview_voice` write `data/out/designs/<design_id>/candidate-01.wav`.
`speak` and `download_speech` write `data/out/<voice_id>-<speech_id>.wav`.
`download_voice` writes `data/out/voices/<voice_id>/`.
`preview_template` writes `data/out/templates/<template_id>.wav`.
The files are written on the server under `data/out`. The agent passes those
paths to the next content step.

## Connect

`bun start.ts` prints the MCP URL. On the server itself it is
`http://127.0.0.1:8180/mcp`. From another machine it is
`http://<server-ip>:8180/mcp`.

When `server.token` is set, send it as `Authorization: Bearer <token>`. The
same token guards `/mcp` and `/v1`. `GET /health` stays open.

```json
{
  "mcpServers": {
    "voice-design": {
      "url": "http://<server-ip>:8180/mcp",
      "headers": {
        "Authorization": "Bearer change-me"
      }
    }
  }
}
```

Copy [mcp.json.example](../mcp.json.example). This repository includes
`.cursor/mcp.json` for Cursor on this machine.
