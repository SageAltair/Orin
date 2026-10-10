import { useRef, useState } from "react";
import { Mic, Plus } from "lucide-react";
import type { CaptureSuggestion as CaptureSuggestionType, Energy } from "./types";

type Recognition = { start: () => void; onresult: ((event: { results: ArrayLike<ArrayLike<{ transcript: string }>> }) => void) | null; onerror: (() => void) | null };
type RecognitionWindow = Window & { SpeechRecognition?: new () => Recognition; webkitSpeechRecognition?: new () => Recognition };
type Suggestion = CaptureSuggestionType;

export function Capture({ onSave, onSuggest, busy, onDone }: {
  onSave: (title: string, details: { first_step?: string; energy_level?: Energy }) => Promise<unknown>;
  onSuggest: (title: string) => Promise<Suggestion>;
  busy: boolean; onDone: () => void;
}) {
  const [title, setTitle] = useState("");
  const [firstStep, setFirstStep] = useState("");
  const [energy, setEnergy] = useState<Energy | "">("");
  const [suggestion, setSuggestion] = useState<Suggestion | null>(null);
  const [suggesting, setSuggesting] = useState(false);
  const [message, setMessage] = useState("");
  const input = useRef<HTMLTextAreaElement>(null);
  const listen = () => {
    const RecognitionApi = (window as RecognitionWindow).SpeechRecognition ?? (window as RecognitionWindow).webkitSpeechRecognition;
    if (!RecognitionApi) { setMessage("Voice capture is not available in this browser. You can type instead."); return; }
    const recognition = new RecognitionApi();
    recognition.onresult = event => setTitle(current => `${current}${current ? " " : ""}${event.results[0]?.[0]?.transcript ?? ""}`);
    recognition.onerror = () => setMessage("Voice capture stopped. Your typed text is still here.");
    recognition.start();
  };
  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    const saved = await onSave(title.trim(), { first_step: firstStep.trim() || undefined, energy_level: energy || undefined });
    if (saved) { setTitle(""); setFirstStep(""); setEnergy(""); setSuggestion(null); setMessage("Saved. One small step is ready on Now."); onDone(); }
  };
  const suggest = async () => {
    if (!title.trim()) return;
    setSuggesting(true); setMessage("");
    try { setSuggestion(await onSuggest(title.trim())); }
    catch { setSuggestion(null); setMessage("Suggestions are unavailable right now. Your capture is still here; you can save or keep typing."); }
    finally { setSuggesting(false); }
  };

  return <section className="focus-card focus-capture" aria-labelledby="capture-heading">
    <span className="focus-eyebrow">ONE THING AT A TIME</span><h1 id="capture-heading">What would you like to do?</h1>
    <p>Write it in your own words. You don’t need to plan it yet.</p>
    <form onSubmit={submit}>
      <label className="sr-only" htmlFor="focus-capture-input">What would you like to remember?</label>
      <textarea ref={input} id="focus-capture-input" autoFocus value={title} onChange={event => setTitle(event.target.value)} placeholder="For example: reply to the message" rows={3} />
      {suggestion && <div className="focus-suggestion" role="group" aria-label="Optional task suggestions">
        <p>Optional suggestions. You can edit them before saving.</p>
        <div className="focus-action-row"><button type="button" className="focus-secondary" onClick={() => { setTitle(suggestion.title); setFirstStep(suggestion.first_step); setEnergy(suggestion.energy_level); setSuggestion(null); }}>Use suggestions</button><button type="button" className="focus-text-button" onClick={() => setSuggestion(null)}>Keep my words</button></div>
      </div>}
      <details className="focus-settings focus-capture-help">
        <summary>Need help with words or the first step?</summary>
        <p>Orin can offer an optional suggestion. You can edit it or ignore it.</p>
        <div className="focus-action-row"><button type="button" className="focus-secondary" onClick={listen} aria-label="Capture by voice"><Mic size={18} /> Speak instead</button><button type="button" className="focus-secondary" onClick={() => void suggest()} disabled={suggesting || !title.trim()}>{suggesting ? "Thinking…" : "Suggest a first step"}</button></div>
        {(firstStep || energy) && <div className="focus-capture-details">
          <label className="focus-field-label" htmlFor="capture-first-step">First step (optional)</label>
          <input id="capture-first-step" value={firstStep} onChange={event => setFirstStep(event.target.value)} maxLength={500} />
          <label className="focus-field-label" htmlFor="capture-energy">Energy (optional)</label>
          <select id="capture-energy" value={energy} onChange={event => setEnergy(event.target.value as Energy | "")}><option value="">Choose later</option><option value="low">Low</option><option value="medium">Medium</option><option value="high">High</option></select>
        </div>}
      </details>
      <div className="focus-action-row"><button type="submit" className="focus-primary" disabled={busy || !title.trim()}><Plus size={18} /> Save and continue</button></div>
    </form>
    {message && <p role="status" className="focus-quiet-message">{message}</p>}
  </section>;
}
