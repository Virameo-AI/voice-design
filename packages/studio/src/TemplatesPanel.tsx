import { useEffect, useState } from "react";
import type { Api, VoiceTemplate } from "./api";
import { errorMessage, Field, LANGUAGES } from "./common";
import { TemplateCards } from "./TemplateCards";

export function TemplatesView({ api, onUse }: { api: Api; onUse: (template: VoiceTemplate) => void }) {
  const [templates, setTemplates] = useState<VoiceTemplate[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [confirmId, setConfirmId] = useState<string | null>(null);

  async function reload() {
    setTemplates(await api.templates());
  }

  useEffect(() => {
    let alive = true;
    api
      .templates()
      .then((rows) => alive && setTemplates(rows))
      .catch((err) => alive && setError(errorMessage(err)));
    return () => {
      alive = false;
    };
  }, [api]);

  async function run(action: () => Promise<void>) {
    setError(null);
    try {
      await action();
      await reload();
    } catch (err) {
      setError(errorMessage(err));
    }
  }

  return (
    <section className="view" aria-label="Templates">
      <div className="subhero">
        <span className="eyebrow">Your voice studio / 04</span>
        <h1>
          Recipes you can <em>hear first.</em>
        </h1>
        <p className="lead">Play a sample, then load the settings into Create. Change the seed or the wording before you generate.</p>
      </div>
      {error && <p className="error">{error}</p>}
      <TemplateCards
        api={api}
        templates={templates}
        layout="grid"
        onLoad={onUse}
        actions={(template) => (
          <TemplateActions
            template={template}
            confirm={confirmId === template.id}
            onUse={() => onUse(template)}
            onDuplicate={() => void run(() => api.duplicateTemplate(template.id).then(() => undefined))}
            onAskDelete={() => setConfirmId(template.id)}
            onCancelDelete={() => setConfirmId(null)}
            onDelete={() => void run(() => api.deleteTemplate(template.id))}
            onSave={(body) => void run(() => api.updateTemplate(template.id, body).then(() => undefined))}
          />
        )}
      />
    </section>
  );
}

function TemplateActions({
  template,
  confirm,
  onUse,
  onDuplicate,
  onAskDelete,
  onCancelDelete,
  onDelete,
  onSave,
}: {
  template: VoiceTemplate;
  confirm: boolean;
  onUse: () => void;
  onDuplicate: () => void;
  onAskDelete: () => void;
  onCancelDelete: () => void;
  onDelete: () => void;
  onSave: (body: Pick<VoiceTemplate, "name" | "role" | "instruct" | "text" | "language" | "candidates" | "seed_start">) => void;
}) {
  const [name, setName] = useState(template.name);
  const [role, setRole] = useState(template.role);
  const [instruct, setInstruct] = useState(template.instruct);
  const [text, setText] = useState(template.text);
  const [language, setLanguage] = useState(template.language);
  const [candidates, setCandidates] = useState(template.candidates);
  const [seedStart, setSeedStart] = useState(template.seed_start);

  return (
    <div className="template-actions">
      <button type="button" className="primary" onClick={onUse}>
        Use this template
      </button>
      <button type="button" className="secondary" onClick={onDuplicate}>
        Duplicate
      </button>
      {template.origin === "user" &&
        (confirm ? (
          <button type="button" className="secondary" onClick={onDelete}>
            Confirm delete
          </button>
        ) : (
          <button type="button" className="secondary" onClick={onAskDelete}>
            Delete
          </button>
        ))}
      {template.origin === "user" && confirm && (
        <button type="button" className="secondary" onClick={onCancelDelete}>
          Keep it
        </button>
      )}
      {template.origin === "user" && (
        <details className="tech">
          <summary>Edit</summary>
          <Field label="Name">
            <input value={name} onChange={(e) => setName(e.target.value)} maxLength={80} />
          </Field>
          <Field label="Card line">
            <input value={role} onChange={(e) => setRole(e.target.value)} maxLength={120} />
          </Field>
          <Field label="Voice description">
            <textarea value={instruct} onChange={(e) => setInstruct(e.target.value)} maxLength={2000} />
          </Field>
          <Field label="Preview script">
            <textarea value={text} onChange={(e) => setText(e.target.value)} maxLength={1000} />
          </Field>
          <div className="form-row">
            <Field label="Language">
              <select value={language} onChange={(e) => setLanguage(e.target.value)}>
                {LANGUAGES.map((item) => (
                  <option key={item}>{item}</option>
                ))}
              </select>
            </Field>
            <Field label="Candidates">
              <input type="number" min={1} max={8} value={candidates} onChange={(e) => setCandidates(Number(e.target.value))} />
            </Field>
          </div>
          <Field label="First seed">
            <input type="number" min={0} value={seedStart} onChange={(e) => setSeedStart(Number(e.target.value))} />
          </Field>
          <button
            type="button"
            className="secondary"
            onClick={() => onSave({ name: name.trim(), role: role.trim(), instruct: instruct.trim(), text: text.trim(), language, candidates, seed_start: seedStart })}
            disabled={!name.trim() || !role.trim() || !instruct.trim() || !text.trim()}
          >
            Save changes
          </button>
        </details>
      )}
    </div>
  );
}
