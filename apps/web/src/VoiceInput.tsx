import { useState } from "react";
import { Mic, MicOff } from "lucide-react";

type Recognition = { lang: string; interimResults: boolean; continuous: boolean; start: () => void; stop: () => void; onresult: ((event: { results: ArrayLike<{ 0: { transcript: string } }> }) => void) | null; onend: (() => void) | null; onerror: (() => void) | null };
type RecognitionWindow = Window & { SpeechRecognition?: new () => Recognition; webkitSpeechRecognition?: new () => Recognition };

export function VoiceInput({ value, onChange }: { value: string; onChange: (value: string) => void }) {
  const [listening, setListening] = useState(false);
  const available = typeof window !== "undefined" && Boolean((window as RecognitionWindow).SpeechRecognition ?? (window as RecognitionWindow).webkitSpeechRecognition);
  const listen = () => {
    const Api = (window as RecognitionWindow).SpeechRecognition ?? (window as RecognitionWindow).webkitSpeechRecognition;
    if (!Api) return;
    const recognition = new Api(); recognition.lang = navigator.language || "en"; recognition.interimResults = false; recognition.continuous = false;
    recognition.onresult = event => { const transcript = event.results[0]?.[0]?.transcript?.trim(); if (transcript) onChange(`${value}${value.trim() ? " " : ""}${transcript}`); };
    recognition.onend = () => setListening(false); recognition.onerror = () => setListening(false); setListening(true); recognition.start();
  };
  if (!available) return null;
  return <button type="button" className="voice-input" aria-label={listening ? "Listening for voice input" : "Use voice input"} onClick={listen} disabled={listening}>{listening ? <MicOff size={16} /> : <Mic size={16} />}</button>;
}
