import type { ReactNode } from "react";
import type { Api, VoiceTemplate } from "./api";
import { SoundClip } from "./SoundClip";

export function TemplateCards({
  api,
  templates,
  layout,
  loadedId,
  onLoad,
  actions,
}: {
  api: Api;
  templates: VoiceTemplate[];
  layout: "row" | "grid";
  loadedId?: string | null;
  onLoad: (template: VoiceTemplate) => void;
  actions?: (template: VoiceTemplate) => ReactNode;
}) {
  return (
    <div className={layout === "row" ? "template-row" : "template-grid"}>
      {templates.map((template) => (
        <article key={template.id} className={template.id === loadedId ? "template-card loaded" : "template-card"}>
          <button type="button" className="template-load" onClick={() => onLoad(template)}>
            <span className="tiny-tag">{template.origin === "builtin" ? "Default" : "Yours"}</span>
            <strong>{template.name}</strong>
            <span>{template.role}</span>
          </button>
          {template.has_sample && template.sample_url ? (
            <SoundClip
              api={api}
              path={template.sample_url}
              filename={`${template.id}.wav`}
              label={`${template.name} sample`}
              seed={template.seed_start}
            />
          ) : (
            <p className="muted small">No sample yet. Save a take from Create to hear this one.</p>
          )}
          {actions?.(template)}
        </article>
      ))}
    </div>
  );
}
