import { ApiError, request } from "../../api";
import type { CreativeDocumentCard, CreativeIdea, CreativeIdeaLink, CreativeOutlineItem, DocumentCardStatus, IdeaLinkType, OutlineItemKind, OutlineItemStatus } from "@orin/contracts";

export type { CreativeDocumentCard, CreativeIdea, CreativeIdeaLink, CreativeOutlineItem, DocumentCardStatus, IdeaLinkType, OutlineItemKind, OutlineItemStatus };

const errorText = (error: unknown) => error instanceof ApiError ? error.message : "Something went wrong. Please try again.";

/* --- Ideas --- */

export async function fetchIdeas(status: "active" | "archived" | "all" = "active"): Promise<CreativeIdea[]> {
  const params = new URLSearchParams({ status });
  return request<CreativeIdea[]>(`/creative/ideas?${params}`);
}

export async function createIdea(text: string): Promise<CreativeIdea> {
  return request<CreativeIdea>("/creative/ideas", { method: "POST", body: JSON.stringify({ text }) });
}

export async function updateIdea(ideaId: string, text: string): Promise<CreativeIdea> {
  return request<CreativeIdea>(`/creative/ideas/${ideaId}`, { method: "PATCH", body: JSON.stringify({ text }) });
}

export async function fetchIdeaLinks(ideaId: string): Promise<CreativeIdeaLink[]> {
  return request<CreativeIdeaLink[]>(`/creative/ideas/${ideaId}/links`);
}

export async function linkIdeaToDocument(ideaId: string, documentId: string, linkType: IdeaLinkType = "inspires", note?: string): Promise<CreativeIdeaLink> {
  return request<CreativeIdeaLink>(`/creative/ideas/${ideaId}/links`, { method: "POST", body: JSON.stringify({ document_id: documentId, link_type: linkType, note: note ?? null }) });
}

export async function unlinkIdeaFromDocument(ideaId: string, documentId: string, linkType: IdeaLinkType): Promise<void> {
  await request<void>(`/creative/ideas/${ideaId}/links/${documentId}?link_type=${encodeURIComponent(linkType)}`, { method: "DELETE" });
}

/* --- Outline --- */

export async function fetchOutline(projectId: string, parentId?: string): Promise<CreativeOutlineItem[]> {
  const params = new URLSearchParams();
  if (parentId) params.set("parent_id", parentId);
  return request<CreativeOutlineItem[]>(`/creative/projects/${projectId}/outline?${params}`);
}

export async function createOutlineItem(projectId: string, payload: { title: string; kind: OutlineItemKind; parent_id?: string | null; document_id?: string | null; summary?: string; position?: number }): Promise<CreativeOutlineItem> {
  return request<CreativeOutlineItem>(`/creative/projects/${projectId}/outline`, { method: "POST", body: JSON.stringify(payload) });
}

export async function updateOutlineItem(projectId: string, itemId: string, payload: { title?: string; summary?: string | null; status?: OutlineItemStatus; position?: number }): Promise<CreativeOutlineItem> {
  return request<CreativeOutlineItem>(`/creative/projects/${projectId}/outline/${itemId}`, { method: "PATCH", body: JSON.stringify(payload) });
}

/* --- Document cards --- */

export async function fetchCards(projectId: string, cardStatus?: DocumentCardStatus | "all"): Promise<CreativeDocumentCard[]> {
  const params = new URLSearchParams();
  if (cardStatus) params.set("status", cardStatus);
  return request<CreativeDocumentCard[]>(`/creative/projects/${projectId}/cards?${params}`);
}

export async function createCard(projectId: string, payload: { title: string; summary?: string | null; purpose?: string | null; central_question?: string | null; point_of_view?: string | null; status?: DocumentCardStatus; document_id?: string | null; position?: number }): Promise<CreativeDocumentCard> {
  return request<CreativeDocumentCard>(`/creative/projects/${projectId}/cards`, { method: "POST", body: JSON.stringify(payload) });
}

export async function updateCard(projectId: string, cardId: string, payload: Partial<{ title: string; summary: string | null; purpose: string | null; central_question: string | null; point_of_view: string | null; status: DocumentCardStatus; position: number }>): Promise<CreativeDocumentCard> {
  return request<CreativeDocumentCard>(`/creative/projects/${projectId}/cards/${cardId}`, { method: "PATCH", body: JSON.stringify(payload) });
}

/* --- Deterministic AI suggestions (template-based, mirrors the API's _ai_ideas) --- */

export interface StudioSuggestion {
  kind: "explore" | "expand" | "connect" | "challenge";
  label: string;
  prompt: string;
}

export function suggestIdeas(seed: string): StudioSuggestion[] {
  const topic = (seed.trim().split("\n")[0] || "this idea").slice(0, 80);
  return [
    { kind: "explore", label: "Explore", prompt: `What assumptions sit underneath “${topic}”? List three and test each one.` },
    { kind: "expand", label: "Expand", prompt: `Give me three concrete scenes, examples, or sub-questions that grow “${topic}”.` },
    { kind: "connect", label: "Connect", prompt: `Which of my existing notes relate to “${topic}”, and how could they build on it?` },
    { kind: "challenge", label: "Challenge", prompt: `Argue the strongest case against “${topic}”. What would change my mind?` },
  ];
}

export { errorText };
