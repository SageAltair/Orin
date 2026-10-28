import { useState, type FormEvent } from "react";
import { ActionIcon } from "./ActionIcon";
import { ApiError, request, requestBlob } from "./api";

export function AccountPrivacy({ userId }: { userId: string }) {
  const [deleting, setDeleting] = useState(false);
  const [confirmation, setConfirmation] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const explain = (e: unknown) =>
    e instanceof ApiError
      ? e.message
      : "The privacy request could not be completed.";
  const download = async () => {
    setBusy(true);
    setError("");
    try {
      const blob = await requestBlob("/privacy/export");
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = "orin-account.zip";
      link.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
      setNotice("Your account export is ready. Keep it somewhere private.");
    } catch (e) {
      setError(explain(e));
    } finally {
      setBusy(false);
    }
  };
  const remove = async (event: FormEvent) => {
    event.preventDefault();
    if (confirmation !== "DELETE") return;
    setBusy(true);
    setError("");
    try {
      await request("/privacy/account", {
        method: "DELETE",
        body: JSON.stringify({ current_password: password, confirmation }),
      });
      for (const key of Object.keys(localStorage))
        if (key.startsWith(`orin:writing:draft:${userId}:`))
          localStorage.removeItem(key);
      location.reload();
    } catch (e) {
      setError(explain(e));
      setBusy(false);
    }
  };
  return (
    <section className="settings-section" aria-label="Account privacy">
      <div className="section-heading">
        <div>
          <span className="eyebrow">PRIVACY</span>
          <h2>Your work belongs to you.</h2>
        </div>
        <ActionIcon name="shield" size={20} />
      </div>
      <p>
        Export your notes, projects, tasks, histories and attachments. Password
        hashes and integration credentials are excluded.
      </p>
      {error && (
        <p className="api-error" role="alert">
          {error}
        </p>
      )}
      {notice && <p role="status">{notice}</p>}
      <button
        className="secondary-button"
        disabled={busy}
        onClick={() => void download()}
      >
        <ActionIcon name="download" size={15} />{" "}
        {busy && !deleting ? "Preparing export…" : "Export my account"}
      </button>
      <details className="account-danger">
        <summary>Delete account</summary>
        <p>
          This permanently removes your account, saved work and attachments.
          Export first if you want a copy.
        </p>
        {!deleting ? (
          <button
            className="secondary-button"
            onClick={() => setDeleting(true)}
          >
            Review account deletion
          </button>
        ) : (
          <form className="preference-controls" onSubmit={remove}>
            <label>
              Current password
              <input
                type="password"
                autoComplete="current-password"
                required
                value={password}
                onChange={(e) => setPassword(e.target.value)}
              />
            </label>
            <label>
              Type DELETE to confirm
              <input
                aria-label="Deletion confirmation"
                value={confirmation}
                onChange={(e) => setConfirmation(e.target.value)}
                autoComplete="off"
              />
            </label>
            <button
              className="danger-button"
              disabled={busy || confirmation !== "DELETE" || !password}
            >
              {busy ? "Deleting…" : "Permanently delete account"}
            </button>
            <button
              type="button"
              className="text-action"
              onClick={() => {
                setDeleting(false);
                setPassword("");
                setConfirmation("");
              }}
            >
              Cancel
            </button>
          </form>
        )}
      </details>
    </section>
  );
}
