import { expect, test } from "bun:test";
import { safeName, speechPath, voiceFileName } from "../src/files.ts";
import { TOOL_NAMES } from "../src/tools.ts";

test("file names stay inside the output directory", () => {
  expect(safeName("candidate-01.wav")).toBe("candidate-01.wav");
  expect(() => safeName("../secret.wav")).toThrow("bad file name");
  expect(() => safeName("a/b.wav")).toThrow("bad file name");
  expect(voiceFileName("master.wav")).toBe("master.wav");
  expect(() => voiceFileName("other.wav")).toThrow("voice files");
  expect(speechPath("/tmp/out", "narrator-v1", "job_1")).toBe("/tmp/out/narrator-v1-job_1.wav");
});

test("the agent tools cover design, preview, lock, speech, templates, and profile", () => {
  expect(TOOL_NAMES).toContain("design_voice");
  expect(TOOL_NAMES).toContain("preview_voice");
  expect(TOOL_NAMES).toContain("lock_voice");
  expect(TOOL_NAMES).toContain("speak");
  expect(TOOL_NAMES).toContain("download_speech");
  expect(TOOL_NAMES).toContain("save_template");
  expect(TOOL_NAMES).toContain("save_profile_voice");
  expect(new Set(TOOL_NAMES).size).toBe(TOOL_NAMES.length);
});

test("the library tools cover playgrounds, versions, styles, narrations, and downloads", () => {
  for (const name of [
    "create_playground",
    "run_playground",
    "copy_playground",
    "update_voice",
    "copy_voice",
    "list_voice_versions",
    "save_style",
    "create_narration",
    "update_narration",
    "render_saved_narration",
    "copy_narration",
    "download_narration",
    "list_downloads",
  ]) {
    expect(TOOL_NAMES).toContain(name);
  }
});
