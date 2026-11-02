import { beforeEach, describe, expect, it, vi } from "vitest";
import { revokeLocalWindowsCompanion } from "./windowsReminderLocalControl";

const lease = {
  sessionId: "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
  generation: "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
};

describe("optional local Windows companion revocation", () => {
  beforeEach(() => {
    vi.stubGlobal("crypto", {
      subtle: {
        importKey: vi.fn().mockResolvedValue("test-key"),
        sign: vi.fn().mockResolvedValue(Uint8Array.from([0, 1, 254, 255]).buffer),
      },
    });
  });

  it("uses an HMAC proof without sending the generation to a loopback service", async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce({ ok: true, json: async () => ({ nonce: "abcdef0123456789abcdef0123456789" }) })
      .mockResolvedValueOnce({ status: 204 });
    vi.stubGlobal("fetch", fetchMock);
    await expect(revokeLocalWindowsCompanion(lease)).resolves.toBe(true);
    expect(fetchMock).toHaveBeenCalledTimes(2);
    const [challengeUrl, challengeOptions] = fetchMock.mock.calls[0];
    expect(challengeUrl).toBe("http://127.0.0.1:18765/challenge");
    expect(challengeOptions.credentials).toBe("omit");
    const [revokeUrl, revokeOptions] = fetchMock.mock.calls[1];
    expect(revokeUrl).toBe("http://127.0.0.1:18765/revoke");
    expect(revokeOptions.method).toBe("POST");
    expect(revokeOptions.credentials).toBe("omit");
    expect(revokeOptions.body).not.toContain(lease.generation);
    expect(JSON.parse(revokeOptions.body)).toEqual({
      nonce: "abcdef0123456789abcdef0123456789",
      session_id: lease.sessionId,
      proof: "0001feff",
    });
    const signInput = vi.mocked(crypto.subtle.sign).mock.calls[0][2];
    expect(new TextDecoder().decode(signInput as ArrayBuffer)).toBe(
      "abcdef0123456789abcdef0123456789|" + lease.sessionId,
    );
  });

  it("fails safely when no local companion is listening", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("connection refused")));
    await expect(revokeLocalWindowsCompanion(lease)).resolves.toBe(false);
  });

  it("does not send a proof for a malformed challenge", async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => ({ nonce: "bad" }) });
    vi.stubGlobal("fetch", fetchMock);
    await expect(revokeLocalWindowsCompanion(lease)).resolves.toBe(false);
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });
});


describe("foreground local browser heartbeat", () => {
  it("authenticates the heartbeat with a domain-separated proof", async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce({ ok: true, json: async () => ({ nonce: "abcdef0123456789abcdef0123456789" }) })
      .mockResolvedValueOnce({ status: 204 });
    vi.stubGlobal("fetch", fetchMock);
    vi.stubGlobal("crypto", { subtle: {
      importKey: vi.fn().mockResolvedValue("key"),
      sign: vi.fn().mockResolvedValue(Uint8Array.from([1, 2]).buffer),
    } });
    const { heartbeatLocalWindowsCompanion } = await import("./windowsReminderLocalControl");
    await expect(heartbeatLocalWindowsCompanion(lease)).resolves.toBe(true);
    expect(fetchMock.mock.calls[1][0]).toBe("http://127.0.0.1:18765/heartbeat");
    expect(new TextDecoder().decode(vi.mocked(crypto.subtle.sign).mock.calls[0][2] as ArrayBuffer))
      .toBe("abcdef0123456789abcdef0123456789|" + lease.sessionId + "|heartbeat");
  });
});

describe("unreachable local heartbeat", () => {
  it("never claims foreground presence without a listener acknowledgement", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("connection refused")));
    const { heartbeatLocalWindowsCompanion } = await import("./windowsReminderLocalControl");
    await expect(heartbeatLocalWindowsCompanion(lease)).resolves.toBe(false);
  });
});
