# MCP

Agents call voice-design at `http://<server>:8180/mcp`. The studio serves that
endpoint. It calls the engine on this machine and does not load a model.
Start the stack with `bun start.ts`.

The tools mirror the API, so an agent and a person see the same playgrounds,
voices, versions, styles, and narrations. The server's instructions give the
flow:

> create_playground (or design_voice) → run_playground → get_job until
> succeeded → lock_voice → create_narration →
> render_saved_narration → get_job → download_narration.

## How long jobs behave

Design and render return a job id at once. `get_job` returns
`status`, `progress` (`phase`, `detail`, `completed`, `total`), and `next`, a
sentence that tells the agent what to do: poll again in 15 seconds, download,
or resubmit because the server restarted. `cancel_job` works only while a job
is queued. Submitting the same render again while it runs returns an error
that names the running job.

`design_voice`, `lock_voice`, and `speak` block until the result exists (20,
10, and 10 minutes). If they time out, the error names the job and the agent
continues with `get_job`.

Downloads write files on the server under `data/out` and return absolute
paths. Tool results never contain audio bytes. A ten-minute narration is
about 30 MB.

## Tools

| Tool | Section | What the agent gets back |
| --- | --- | --- |
| `list_playgrounds`, `create_playground`, `get_playground`, `update_playground`, `copy_playground`, `delete_playground` | Playgrounds | Saved design workspaces. `get_playground` includes every run with its job and the voices kept from it. |
| `run_playground` | Playgrounds | Queues a design job from the playground config (overrides optional, `save=false` keeps them out of the draft). Returns the job summary. |
| `design_voice`, `list_designs`, `get_design`, `preview_voice` | Voice design | A design without a playground. `design_voice` waits and returns each take's path. |
| `lock_voice` | Voices | Keeps a take as `voice_id`, version 1. Linked to the playground when the design came from one. |
| `list_voices`, `get_voice`, `update_voice`, `copy_voice`, `delete_voice`, `download_voice` | Voices | Library, one voice with its versions, rename/notes/favorite/archive/current version, a copy whose version 1 is any version, delete (refused while narrations use it), master path. |
| `list_voice_versions`, `download_voice_version` | Versions | Version 1, the kept take, and a version master's path. |
| `list_styles`, `save_style`, `update_style`, `delete_style` | Styles | Narration presets. Built-ins stay as shipped; `save_style` with `copy_of` makes an editable one. |
| `list_narrations`, `create_narration`, `get_narration`, `update_narration`, `copy_narration`, `delete_narration` | Narrations | Drafts and rendered narrations. A draft is fully editable; after render only title and notes change; copy makes a new draft. |
| `render_saved_narration` | Narrations | Queues the render and freezes the draft. Returns the job summary. |
| `render_narration` | Speech | A one-shot render without a draft: voice, optional version, style, script. Returns the job summary. |
| `speak`, `list_speech`, `get_speech`, `download_speech` | Speech | Short lines in a voice (optional version). `download_speech` works for speech and render jobs. |
| `download_narration` | Narrations | Writes the final WAV and returns its path. Refuses drafts and narrations still rendering. |
| `list_downloads` | Downloads | Every WAV the engine holds with its url: narrations, voice masters, speech. |
| `list_templates`, `get_template`, `save_template`, `update_template`, `duplicate_template`, `delete_template`, `preview_template`, `set_template_sample` | Templates | Voice recipes for later designs. |
| `list_profile`, `save_profile_voice`, `remove_profile_voice` | Profile | Kept voices. `update_voice` with `favorite` is the same shelf. |
| `list_jobs`, `get_job`, `cancel_job`, `delete_job` | Jobs | The shared queue. |

Files on the server:

```text
data/out/designs/<design_id>/candidate-01.wav      design_voice, preview_voice
data/out/voices/<voice_id>/master.wav               download_voice
data/out/voices/<voice_id>/<voice_id>-v2.wav        download_voice_version
data/out/narrations/<voice_id>-<narration_id>.wav   download_narration
data/out/<voice_id>-<job_id>.wav                    speak, download_speech
data/out/templates/<template_id>.wav                preview_template
```

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

## Tests

```bash
bun test packages/mcp/tests
```

The tests check that every tool name is unique, that `tools/list` over the
HTTP transport returns every tool with a description, and that a call against
a stopped engine returns a readable error instead of a crash.
