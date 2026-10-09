import { useRef, useState } from "react";
import { Mic, Plus } from "lucide-react";

type Recognition = { start: () => void; onresult: ((event: { results: ArrayLike<ArrayLike<{ transcript: string }>> }) => void) | null; onerror: (() => void) | null };
type RecognitionWindow = Window & { SpeechRecognition?: new () => Recognition; webkitSpeechRecognition?: new () => Recognition };

export function Capture({ onSave, busy, onDone }: { onSave: (title: string) => Promise<unknown>; busy: boolean; onDone: () => void }) {
  const [title, setTitle] = useState("");
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
    const saved = await onSave(title.trim());
    if (saved) { setTitle(""); setMessage("Saved. One small step is ready on Now."); onDone(); }
  };

  return <section className="focus-card focus-capture" aria-labelledby="capture-heading">
    <span className="focus-eyebrow">CAPTURE</span><h1 id="capture-heading">Let it land here.</h1>
    <p>You can decide what it means later.</p>
    <form onSubmit={submit}>
      <label className="sr-only" htmlFor="focus-capture-input">What would you like to remember?</label>
      <textarea ref={input} id="focus-capture-input" autoFocus value={title} onChange={event => setTitle(event.target.value)} placeholder="Write or say anything" rows={3} />
      <div className="focus-action-row"><button type="button" className="focus-secondary" onClick={listen} aria-label="Capture by voice"><Mic size={18} /> Voice</button><button type="submit" className="focus-primary" disabled={busy}><Plus size={18} /> Save</button></div>
    </form>
    {message && <p role="status" className="focus-quiet-message">{message}</p>}
  </section>;
}
