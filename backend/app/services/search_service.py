"""Knowledge Vault: Cross-modal semantic search service powered by ChromaDB, Multilingual E5/BGE-M3, and SigLIP."""

from __future__ import annotations

import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import chromadb
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.logging import get_logger
from app.models.attachment import Attachment
from app.models.conversation import Conversation
from app.models.image_analysis import ImageAnalysis
from app.models.transcript import Transcript
from app.schemas.search import SearchResult, SearchStats
from app.schemas.vision import ImageAnalysisRead
from app.services.embedding_service import get_embedding_service
from app.services.image_embedding_service import get_image_embedding_service
from app.services.llm_service import get_llm_service

logger = get_logger(__name__)


def _build_deep_link(
    conversation_id: str | None,
    attachment_id: str | None = None,
    start: float | None = None,
) -> str:
    """Format deep link navigating directly to conversation and media timestamp."""
    base = f"/conversations/{conversation_id or 'unknown'}"
    params: list[str] = []
    if attachment_id:
        params.append(f"attachment={attachment_id}")
    if start is not None and start >= 0:
        params.append(f"t={int(start)}")
    if params:
        return f"{base}?{'&'.join(params)}"
    return base


class SearchService:
    """Singleton Knowledge Vault managing cross-modal indexing and reciprocal rank fusion search."""

    _instance: SearchService | None = None

    def __init__(self) -> None:
        self.persist_dir = settings.VAULT_CHROMA_PATH.resolve()
        self.persist_dir.mkdir(parents=True, exist_ok=True)
        self.chroma_client = chromadb.PersistentClient(path=str(self.persist_dir))

        self.text_embedder = get_embedding_service()
        self.image_embedder = get_image_embedding_service()

        self._text_col: Any = None
        self._image_col: Any = None

    @classmethod
    def get_instance(cls) -> SearchService:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @property
    def vault_text(self) -> Any:
        """Retrieve or initialize the persistent vault_text collection."""
        if self._text_col is None:
            self._text_col = self.chroma_client.get_or_create_collection(
                name="vault_text",
                metadata={
                    "description": "Multilingual text embeddings for transcripts, captions, and messages"
                },
            )
        return self._text_col

    @property
    def vault_images(self) -> Any:
        """Retrieve or initialize the persistent vault_images collection."""
        if self._image_col is None:
            self._image_col = self.chroma_client.get_or_create_collection(
                name="vault_images",
                metadata={
                    "description": "SigLIP image embeddings for cross-modal visual retrieval"
                },
            )
        return self._image_col

    # -------------------------------------------------------------------------
    # INDEXING METHODS
    # -------------------------------------------------------------------------
    def index_transcript(
        self,
        user_id: str,
        conversation_id: str | None,
        attachment_id: str,
        transcript_data: dict[str, Any] | Transcript,
    ) -> None:
        """Index transcript segments and analytical action items/decisions into vault_text."""
        try:
            if isinstance(transcript_data, Transcript):
                segments = transcript_data.segments or []
                lang = transcript_data.language or "en"
                insights = transcript_data.insights or {}
                full_text = transcript_data.text
            else:
                segments = transcript_data.get("segments") or []
                lang = transcript_data.get("language") or "en"
                insights = transcript_data.get("insights") or {}
                full_text = transcript_data.get("text", "")

            created_iso = datetime.now(UTC).isoformat()
            ids: list[str] = []
            docs: list[str] = []
            metas: list[dict[str, Any]] = []

            # 1. Index transcript segments
            for i, seg in enumerate(segments):
                text = seg.get("text", "").strip()
                if not text:
                    continue
                start = float(seg.get("start", 0.0))
                end = float(seg.get("end", start + 1.0))
                seg_id = f"aud_{attachment_id}_seg_{i}"

                ids.append(seg_id)
                docs.append(text)
                metas.append(
                    {
                        "user_id": str(user_id),
                        "conversation_id": str(conversation_id or ""),
                        "attachment_id": str(attachment_id),
                        "modality": "audio",
                        "start": start,
                        "end": end,
                        "language": str(lang),
                        "created_at": created_iso,
                        "snippet": text[:200],
                        "doc_type": "transcript_segment",
                    }
                )

            # Fallback if no granular segments were parsed
            if not ids and full_text.strip():
                ids.append(f"aud_{attachment_id}_full")
                docs.append(full_text.strip()[:1000])
                metas.append(
                    {
                        "user_id": str(user_id),
                        "conversation_id": str(conversation_id or ""),
                        "attachment_id": str(attachment_id),
                        "modality": "audio",
                        "start": 0.0,
                        "end": 0.0,
                        "language": str(lang),
                        "created_at": created_iso,
                        "snippet": full_text.strip()[:200],
                        "doc_type": "transcript_full",
                    }
                )

            # 2. Index meeting decisions and action items if present in insights
            meeting_insights = insights.get("meeting_insights") or insights
            if isinstance(meeting_insights, dict):
                decisions = meeting_insights.get("decisions") or []
                for idx, dec in enumerate(decisions):
                    ids.append(f"aud_{attachment_id}_dec_{idx}")
                    docs.append(f"Meeting Decision: {dec}")
                    metas.append(
                        {
                            "user_id": str(user_id),
                            "conversation_id": str(conversation_id or ""),
                            "attachment_id": str(attachment_id),
                            "modality": "audio",
                            "start": 0.0,
                            "end": 0.0,
                            "language": str(lang),
                            "created_at": created_iso,
                            "snippet": str(dec)[:200],
                            "doc_type": "meeting_decision",
                        }
                    )

                action_items = meeting_insights.get("action_items") or []
                for idx, item in enumerate(action_items):
                    if isinstance(item, dict):
                        task = item.get("task", "")
                        owner = item.get("owner", "Unassigned")
                        item_text = f"Action Item ({owner}): {task}"
                    else:
                        item_text = f"Action Item: {item}"
                    ids.append(f"aud_{attachment_id}_act_{idx}")
                    docs.append(item_text)
                    metas.append(
                        {
                            "user_id": str(user_id),
                            "conversation_id": str(conversation_id or ""),
                            "attachment_id": str(attachment_id),
                            "modality": "audio",
                            "start": 0.0,
                            "end": 0.0,
                            "language": str(lang),
                            "created_at": created_iso,
                            "snippet": item_text[:200],
                            "doc_type": "meeting_action_item",
                        }
                    )

            if ids:
                embs, _ = self.text_embedder.embed_documents(docs)
                self.vault_text.upsert(ids=ids, documents=docs, embeddings=embs, metadatas=metas)
                logger.info(
                    "Indexed transcript to Knowledge Vault",
                    attachment_id=attachment_id,
                    items_count=len(ids),
                )

        except Exception as e:
            logger.error(
                "Failed indexing transcript to Knowledge Vault",
                attachment_id=attachment_id,
                error=str(e),
            )

    def index_image_analysis(
        self,
        user_id: str,
        conversation_id: str | None,
        attachment_id: str,
        analysis_data: dict[str, Any] | ImageAnalysis | ImageAnalysisRead,
        image_path: Path | str | bytes | None = None,
    ) -> None:
        """Index image caption/OCR into vault_text and SigLIP visual embedding into vault_images."""
        try:
            if isinstance(analysis_data, (ImageAnalysis, ImageAnalysisRead)):
                caption = analysis_data.caption or ""
                ocr_text = analysis_data.ocr_text or ""
            elif isinstance(analysis_data, dict):
                caption = analysis_data.get("caption") or ""
                ocr_text = analysis_data.get("ocr_text") or ""
            else:
                caption = getattr(analysis_data, "caption", "") or ""
                ocr_text = getattr(analysis_data, "ocr_text", "") or ""

            created_iso = datetime.now(UTC).isoformat()

            # 1. Index caption and OCR to vault_text
            text_ids: list[str] = []
            text_docs: list[str] = []
            text_metas: list[dict[str, Any]] = []

            if caption.strip():
                text_ids.append(f"img_{attachment_id}_cap")
                text_docs.append(f"Image Caption: {caption.strip()}")
                text_metas.append(
                    {
                        "user_id": str(user_id),
                        "conversation_id": str(conversation_id or ""),
                        "attachment_id": str(attachment_id),
                        "modality": "image",
                        "start": -1.0,
                        "end": -1.0,
                        "language": "en",
                        "created_at": created_iso,
                        "snippet": caption[:200],
                        "doc_type": "image_caption",
                    }
                )

            if ocr_text.strip():
                text_ids.append(f"img_{attachment_id}_ocr")
                text_docs.append(f"Image OCR Text: {ocr_text.strip()}")
                text_metas.append(
                    {
                        "user_id": str(user_id),
                        "conversation_id": str(conversation_id or ""),
                        "attachment_id": str(attachment_id),
                        "modality": "image",
                        "start": -1.0,
                        "end": -1.0,
                        "language": "en",
                        "created_at": created_iso,
                        "snippet": ocr_text[:200],
                        "doc_type": "image_ocr",
                    }
                )

            if text_ids:
                embs, _ = self.text_embedder.embed_documents(text_docs)
                self.vault_text.upsert(
                    ids=text_ids,
                    documents=text_docs,
                    embeddings=embs,
                    metadatas=text_metas,
                )

            # 2. Index SigLIP image embedding to vault_images
            if image_path is not None:
                img_vectors, _ = self.image_embedder.embed_images([image_path])
                if img_vectors:
                    self.vault_images.upsert(
                        ids=[f"img_{attachment_id}_siglip"],
                        embeddings=[img_vectors[0]],
                        metadatas=[
                            {
                                "user_id": str(user_id),
                                "conversation_id": str(conversation_id or ""),
                                "attachment_id": str(attachment_id),
                                "modality": "image",
                                "start": -1.0,
                                "end": -1.0,
                                "language": "en",
                                "created_at": created_iso,
                                "snippet": caption[:200] or "Image visual vector",
                                "doc_type": "siglip_image",
                            }
                        ],
                    )

            logger.info("Indexed image to Knowledge Vault", attachment_id=attachment_id)
        except Exception as e:
            logger.error(
                "Failed indexing image to Knowledge Vault",
                attachment_id=attachment_id,
                error=str(e),
            )

    def index_message(
        self,
        user_id: str,
        conversation_id: str,
        message_id: str,
        content: str,
        role: str,
        language: str = "en",
    ) -> None:
        """Index a conversational message into vault_text."""
        clean = content.strip()
        if not clean:
            return

        try:
            created_iso = datetime.now(UTC).isoformat()
            doc = f"{role.capitalize()}: {clean}"
            embs, _ = self.text_embedder.embed_documents([doc])
            self.vault_text.upsert(
                ids=[f"msg_{message_id}"],
                documents=[doc],
                embeddings=embs,
                metadatas=[
                    {
                        "user_id": str(user_id),
                        "conversation_id": str(conversation_id),
                        "attachment_id": "",
                        "modality": "text",
                        "start": -1.0,
                        "end": -1.0,
                        "language": str(language),
                        "created_at": created_iso,
                        "snippet": clean[:200],
                        "doc_type": f"message_{role}",
                    }
                ],
            )
        except Exception as e:
            logger.error(
                "Failed indexing message to Knowledge Vault",
                message_id=message_id,
                error=str(e),
            )

    def delete_conversation_entries(self, conversation_id: str) -> None:
        """Purge all entries matching conversation_id from Knowledge Vault collections."""
        try:
            self.vault_text.delete(where={"conversation_id": conversation_id})
        except Exception as e:
            logger.warning("Vault text delete by conversation_id failed or empty", error=str(e))

        try:
            self.vault_images.delete(where={"conversation_id": conversation_id})
        except Exception as e:
            logger.warning("Vault image delete by conversation_id failed or empty", error=str(e))

        logger.info("Purged conversation from Knowledge Vault", conversation_id=conversation_id)

    def delete_attachment_entries(self, attachment_id: str) -> None:
        """Purge all entries matching attachment_id from Knowledge Vault collections."""
        try:
            self.vault_text.delete(where={"attachment_id": attachment_id})
        except Exception as e:
            logger.warning("Vault text delete by attachment_id failed or empty", error=str(e))

        try:
            self.vault_images.delete(where={"attachment_id": attachment_id})
        except Exception as e:
            logger.warning("Vault image delete by attachment_id failed or empty", error=str(e))

        logger.info("Purged attachment from Knowledge Vault", attachment_id=attachment_id)

    # -------------------------------------------------------------------------
    # SEARCH & RANK FUSION METHODS
    # -------------------------------------------------------------------------
    def _matches_filters(
        self,
        meta: dict[str, Any],
        modalities: list[str] | None,
        conversation_id: str | None,
        date_from: datetime | None,
        date_to: datetime | None,
        language: str | None,
    ) -> bool:
        """Filter verification in memory for ChromaDB results."""
        if modalities and meta.get("modality") not in modalities:
            return False
        if conversation_id and meta.get("conversation_id") != conversation_id:
            return False
        if language and meta.get("language") != language:
            return False
        if date_from or date_to:
            created_str = meta.get("created_at")
            if created_str:
                try:
                    dt = datetime.fromisoformat(created_str)
                    if date_from and dt < date_from:
                        return False
                    if date_to and dt > date_to:
                        return False
                except Exception:
                    pass
        return True

    def _llm_rerank(
        self, query: str, candidates: list[SearchResult], top_k: int
    ) -> list[SearchResult]:
        """Perform optional LLM relevance scoring on candidate snippets."""
        if not candidates:
            return candidates

        try:
            llm = get_llm_service()
            candidate_summaries = []
            for i, c in enumerate(candidates[:20]):
                candidate_summaries.append(f"[{i+1}] ({c.modality}) {c.snippet}")

            joined = "\n".join(candidate_summaries)
            prompt = (
                "You are an expert search retrieval ranker. Evaluate the relevance of each candidate "
                "to the user search query on a scale of 0 to 10.\n\n"
                f"Query: {query}\n\n"
                f"Candidates:\n{joined}\n\n"
                "Return a JSON list of numbers representing the index order from most to least relevant, e.g. [3, 1, 2]."
            )
            resp, _ = llm.generate([{"role": "user", "content": prompt}], max_tokens=100)

            # Extract list of indices
            import json
            import re

            m = re.search(r"\[[\d,\s]+\]", resp)
            if m:
                order_indices = json.loads(m.group(0))
                reranked: list[SearchResult] = []
                seen_indices: set[int] = set()
                for idx in order_indices:
                    real_idx = int(idx) - 1
                    if 0 <= real_idx < len(candidates) and real_idx not in seen_indices:
                        reranked.append(candidates[real_idx])
                        seen_indices.add(real_idx)
                for i, c in enumerate(candidates):
                    if i not in seen_indices:
                        reranked.append(c)
                return reranked[:top_k]
        except Exception as e:
            logger.warning(
                "LLM rerank failed; preserving reciprocal rank fusion order",
                error=str(e),
            )

        return candidates[:top_k]

    def search_vault(
        self,
        query: str,
        user_id: str,
        modalities: list[str] | None = None,
        conversation_id: str | None = None,
        top_k: int = 10,
        rerank: bool = False,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
        language: str | None = None,
    ) -> list[SearchResult]:
        """Execute cross-modal search across vault_text and vault_images with Reciprocal Rank Fusion."""
        start_time = time.perf_counter()
        clean_query = query.strip()
        if not clean_query:
            return []

        # RRF dictionary: item_id -> {"score": float, "meta": dict, "snippet": str}
        rrf_scores: dict[str, float] = {}
        items_map: dict[str, dict[str, Any]] = {}
        k_rrf = 60.0

        fetch_limit = min(max(top_k * 3, 20), 100)

        # ---------------------------------------------------------------------
        # 1. Query vault_text (Multilingual Dense Text Embeddings)
        # ---------------------------------------------------------------------
        try:
            q_emb, _ = self.text_embedder.embed_queries([clean_query])
            text_res = self.vault_text.query(
                query_embeddings=q_emb,
                n_results=fetch_limit,
                where={"user_id": user_id},
            )

            text_dists = text_res.get("distances", [[]])[0] if text_res.get("distances") else []
            seen_in_text: set[str] = set()
            if text_res and text_res.get("ids") and text_res["ids"][0]:
                for rank, (item_id, meta, doc) in enumerate(
                    zip(
                        text_res["ids"][0],
                        text_res["metadatas"][0],
                        text_res["documents"][0],
                    )
                ):
                    dist = text_dists[rank] if rank < len(text_dists) else 0.0
                    if dist > 1.75:
                        continue
                    if not self._matches_filters(
                        meta, modalities, conversation_id, date_from, date_to, language
                    ):
                        continue

                    # Distinct deduplication key by attachment or message
                    att_id = meta.get("attachment_id")
                    dedup_key = att_id if (att_id and att_id.strip()) else item_id
                    if dedup_key in seen_in_text:
                        continue
                    seen_in_text.add(dedup_key)

                    sim = max(0.0, 1.0 - (dist / 2.0))
                    score = (1.0 / (k_rrf + rank + 1)) * (0.5 + 0.5 * sim)
                    rrf_scores[dedup_key] = rrf_scores.get(dedup_key, 0.0) + score
                    if dedup_key not in items_map:
                        items_map[dedup_key] = {
                            "id": item_id,
                            "meta": meta,
                            "snippet": meta.get("snippet") or doc[:200],
                        }
        except Exception as e:
            logger.warning("Vault text query failed or empty", error=str(e))

        # ---------------------------------------------------------------------
        # 2. Query vault_images (SigLIP Cross-Modal Text -> Image Space)
        # ---------------------------------------------------------------------
        try:
            img_q_emb, _ = self.image_embedder.embed_text_for_images([clean_query])
            img_res = self.vault_images.query(
                query_embeddings=img_q_emb,
                n_results=fetch_limit,
                where={"user_id": user_id},
            )

            img_dists = img_res.get("distances", [[]])[0] if img_res.get("distances") else []
            seen_in_images: set[str] = set()
            if img_res and img_res.get("ids") and img_res["ids"][0]:
                for rank, (item_id, meta) in enumerate(
                    zip(img_res["ids"][0], img_res["metadatas"][0])
                ):
                    dist = img_dists[rank] if rank < len(img_dists) else 0.0
                    if dist > 1.75:
                        continue
                    if not self._matches_filters(
                        meta, modalities, conversation_id, date_from, date_to, language
                    ):
                        continue

                    att_id = meta.get("attachment_id")
                    dedup_key = att_id if (att_id and att_id.strip()) else item_id
                    if dedup_key in seen_in_images:
                        continue
                    seen_in_images.add(dedup_key)

                    sim = max(0.0, 1.0 - (dist / 2.0))
                    score = (1.0 / (k_rrf + rank + 1)) * (0.5 + 0.5 * sim)
                    rrf_scores[dedup_key] = rrf_scores.get(dedup_key, 0.0) + score
                    if dedup_key not in items_map:
                        items_map[dedup_key] = {
                            "id": item_id,
                            "meta": meta,
                            "snippet": meta.get("snippet") or "Image visual match",
                        }
        except Exception as e:
            logger.warning("Vault image query failed or empty", error=str(e))

        # ---------------------------------------------------------------------
        # 3. Sort by Reciprocal Rank Fusion Score
        # ---------------------------------------------------------------------
        sorted_keys = sorted(rrf_scores.keys(), key=lambda k: rrf_scores[k], reverse=True)

        results: list[SearchResult] = []
        for key in sorted_keys:
            entry = items_map[key]
            meta = entry["meta"]
            start_val = meta.get("start")
            end_val = meta.get("end")
            start_num = (
                float(start_val) if start_val is not None and float(start_val) >= 0 else None
            )
            end_num = float(end_val) if end_val is not None and float(end_val) >= 0 else None

            results.append(
                SearchResult(
                    id=entry["id"],
                    modality=meta.get("modality", "text"),
                    score=round(rrf_scores[key], 5),
                    snippet=entry["snippet"],
                    attachment_id=meta.get("attachment_id") or None,
                    conversation_id=meta.get("conversation_id") or None,
                    start=start_num,
                    end=end_num,
                    deep_link=_build_deep_link(
                        meta.get("conversation_id"),
                        meta.get("attachment_id"),
                        start_num,
                    ),
                )
            )

        # 4. Optional LLM Reranking
        if rerank and len(results) > 1:
            results = self._llm_rerank(clean_query, results, top_k)
        else:
            results = results[:top_k]

        latency_ms = (time.perf_counter() - start_time) * 1000.0
        logger.info(
            "Executed Knowledge Vault search",
            query_len=len(clean_query),
            user_id=user_id,
            results_count=len(results),
            latency_ms=round(latency_ms, 2),
        )
        return results

    def search_by_image(
        self,
        image_input: Path | str | bytes,
        user_id: str,
        modalities: list[str] | None = None,
        conversation_id: str | None = None,
        top_k: int = 10,
        rerank: bool = False,
        filename: str | None = None,
    ) -> list[SearchResult]:
        """Execute visual query across vault_images (SigLIP visual similarity) and text captions."""
        clean_input: Any = image_input
        if isinstance(image_input, bytes) and filename and settings.MOCK_MODELS:
            clean_input = filename

        # 1. Embed query image with SigLIP
        img_vectors, _ = self.image_embedder.embed_images([clean_input])
        if not img_vectors:
            return []

        rrf_scores: dict[str, float] = {}
        items_map: dict[str, dict[str, Any]] = {}
        k_rrf = 60.0

        fetch_limit = min(max(top_k * 3, 20), 100)

        # Query vault_images for visually similar pictures
        try:
            img_res = self.vault_images.query(
                query_embeddings=[img_vectors[0]],
                n_results=fetch_limit,
                where={"user_id": user_id},
            )
            img_dists = img_res.get("distances", [[]])[0] if img_res.get("distances") else []
            seen_in_images: set[str] = set()
            if img_res and img_res.get("ids") and img_res["ids"][0]:
                for rank, (item_id, meta) in enumerate(
                    zip(img_res["ids"][0], img_res["metadatas"][0])
                ):
                    dist = img_dists[rank] if rank < len(img_dists) else 0.0
                    if dist > 1.75:
                        continue
                    if not self._matches_filters(
                        meta, modalities, conversation_id, None, None, None
                    ):
                        continue

                    att_id = meta.get("attachment_id")
                    dedup_key = att_id if (att_id and att_id.strip()) else item_id
                    if dedup_key in seen_in_images:
                        continue
                    seen_in_images.add(dedup_key)

                    sim = max(0.0, 1.0 - (dist / 2.0))
                    score = (1.0 / (k_rrf + rank + 1)) * (0.5 + 0.5 * sim)
                    rrf_scores[dedup_key] = rrf_scores.get(dedup_key, 0.0) + score
                    if dedup_key not in items_map:
                        items_map[dedup_key] = {
                            "id": item_id,
                            "meta": meta,
                            "snippet": meta.get("snippet") or "Visual similarity match",
                        }
        except Exception as e:
            logger.warning("Vault search_by_image query failed", error=str(e))

        sorted_keys = sorted(rrf_scores.keys(), key=lambda k: rrf_scores[k], reverse=True)
        results: list[SearchResult] = []
        for key in sorted_keys[:top_k]:
            entry = items_map[key]
            meta = entry["meta"]
            results.append(
                SearchResult(
                    id=entry["id"],
                    modality="image",
                    score=round(rrf_scores[key], 5),
                    snippet=entry["snippet"],
                    attachment_id=meta.get("attachment_id") or None,
                    conversation_id=meta.get("conversation_id") or None,
                    start=None,
                    end=None,
                    deep_link=_build_deep_link(
                        meta.get("conversation_id"),
                        meta.get("attachment_id"),
                        None,
                    ),
                )
            )
        return results

    def get_stats(self, user_id: str) -> SearchStats:
        """Calculate counts of indexed items in Knowledge Vault for the specified user."""
        try:
            text_items = self.vault_text.get(where={"user_id": user_id})
            text_metas = text_items.get("metadatas") or []

            text_count = sum(1 for m in text_metas if m.get("modality") == "text")
            audio_count = sum(1 for m in text_metas if m.get("modality") == "audio")
            img_caption_count = sum(1 for m in text_metas if m.get("modality") == "image")

            img_items = self.vault_images.get(where={"user_id": user_id})
            img_vectors_count = len(img_items.get("ids") or [])

            total_images = max(img_caption_count, img_vectors_count)
            total = text_count + audio_count + total_images

            return SearchStats(
                total=total,
                text=text_count,
                audio=audio_count,
                image=total_images,
            )
        except Exception as e:
            logger.error("Failed calculating vault stats", user_id=user_id, error=str(e))
            return SearchStats()

    def reindex_user(self, user_id: str, db: Session) -> int:
        """Rebuild user's Knowledge Vault index from database rows."""
        logger.info("Starting user Knowledge Vault re-indexing", user_id=user_id)
        # 1. Purge user entries
        try:
            self.vault_text.delete(where={"user_id": user_id})
        except Exception:
            pass
        try:
            self.vault_images.delete(where={"user_id": user_id})
        except Exception:
            pass

        indexed_count = 0

        # 2. Re-index messages
        conversations = db.query(Conversation).filter(Conversation.user_id == user_id).all()
        for conv in conversations:
            for msg in conv.messages:
                self.index_message(
                    user_id=user_id,
                    conversation_id=conv.id,
                    message_id=msg.id,
                    content=msg.content,
                    role=msg.role,
                    language=msg.language or "en",
                )
                indexed_count += 1

        # 3. Re-index attachments
        attachments = db.query(Attachment).filter(Attachment.user_id == user_id).all()
        for att in attachments:
            if att.type == "audio" and att.transcripts:
                for trans in att.transcripts:
                    self.index_transcript(
                        user_id=user_id,
                        conversation_id=(att.message.conversation_id if att.message else None),
                        attachment_id=att.id,
                        transcript_data=trans,
                    )
                    indexed_count += 1
            elif att.type == "image" and att.image_analyses:
                for analysis in att.image_analyses:
                    self.index_image_analysis(
                        user_id=user_id,
                        conversation_id=(att.message.conversation_id if att.message else None),
                        attachment_id=att.id,
                        analysis_data=analysis,
                        image_path=att.path if Path(att.path).exists() else None,
                    )
                    indexed_count += 1

        logger.info(
            "Completed user Knowledge Vault re-indexing",
            user_id=user_id,
            indexed=indexed_count,
        )
        return indexed_count


def get_search_service() -> SearchService:
    """Retrieve singleton SearchService instance."""
    return SearchService.get_instance()
