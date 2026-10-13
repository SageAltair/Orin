import {
  useEffect,
  useRef,
  useState,
  type FormEvent,
  type ReactNode,
} from "react";
import { X } from "lucide-react";
import { ApiError } from "./api";
export function PlanningForm({
  title,
  children,
  onClose,
  onSave,
  onDelete,
}: {
  title: string;
  children: ReactNode;
  onClose: () => void;
  onSave: () => Promise<void>;
  onDelete?: () => Promise<void>;
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  useEffect(() => {
    const prior = document.activeElement as HTMLElement | null;
    dialog.current?.showModal();
    return () => prior?.focus();
  }, []);
  const run = async (action: () => Promise<void>) => {
    if (busy) return;
    setBusy(true);
    setError("");
    try {
      await action();
      onClose();
    } catch (e) {
      setError(
        e instanceof ApiError
          ? e.message
          : "Could not save. Your changes are still here.",
      );
    } finally {
      setBusy(false);
    }
  };
  return (
    <dialog
      ref={dialog}
      className="planning-dialog"
      onCancel={(e) => {
        e.preventDefault();
        if (!busy) onClose();
      }}
    >
      <form
        onSubmit={(e: FormEvent) => {
          e.preventDefault();
          void run(onSave);
        }}
      >
        <header>
          <div>
            <span className="eyebrow">MAKE SPACE FOR WHAT MATTERS</span>
            <h2>{title}</h2>
          </div>
          <button
            type="button"
            aria-label="Close editor"
            className="text-action"
            disabled={busy}
            onClick={onClose}
          >
            <X size={18} />
          </button>
        </header>
        {error && (
          <p role="alert" className="api-error">
            {error}
          </p>
        )}
        <fieldset disabled={busy}>{children}</fieldset>
        <footer>
          {onDelete && (
            <button
              type="button"
              className="text-action"
              onClick={() => {
                if (confirm("Delete this record? This cannot be undone."))
                  void run(onDelete);
              }}
              disabled={busy}
            >
              Delete
            </button>
          )}
          <button
            type="button"
            className="secondary-button"
            onClick={onClose}
            disabled={busy}
          >
            Cancel
          </button>
          <button className="primary-button" disabled={busy}>
            {busy ? "Saving…" : "Save"}
          </button>
        </footer>
      </form>
    </dialog>
  );
}
