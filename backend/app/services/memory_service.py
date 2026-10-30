"""3-tier conversation memory service (short-term window, rolling summary, ChromaDB retrieval)."""

from __future__ import annotations

import re
from typing import Any

import chromadb
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.logging import get_logger
from app.models.conversation import Conversation
from app.models.message import Message
from app.services.embedding_service import get_embedding_service
from app.services.llm_service import get_llm_service
from app.services.query_rewriter import rewrite_query_if_needed

logger = get_logger(__name__)


def approx_token_count(text: str | None) -> int:
    """Heuristic token count estimation (~4 characters per token)."""
    if not text:
        return 0
    return max(1, len(text) // 4)


class MemoryService:
    """Singleton MemoryService managing short-term windows, summaries, and ChromaDB."""

    _instance: MemoryService | None = None

    def __init__(self) -> None:
        self.persist_dir = settings.CHROMA_PERSIST_DIR.resolve()
        self.persist_dir.mkdir(parents=True, exist_ok=True)
        self.chroma_client = chromadb.PersistentClient(path=str(self.persist_dir))

    @classmethod
    def get_instance(cls) -> MemoryService:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def _sanitize_collection_name(self, conversation_id: str) -> str:
        """Create a valid ChromaDB collection name from conversation UUID."""
        safe_id = re.sub(r"[^a-zA-Z0-9_-]", "_", conversation_id)
        name = f"conv_{safe_id}"
        return name[:63]

    def _get_collection(self, conversation_id: str) -> Any:
        col_name = self._sanitize_collection_name(conversation_id)
        return self.chroma_client.get_or_create_collection(
            name=col_name,
            metadata={"conversation_id": conversation_id},
        )

    def add_message_memory(
        self,
        conversation_id: str,
        message_id: str,
        content: str,
        role: str,
    ) -> None:
        """Index a message into ChromaDB for long-term semantic retrieval."""
        clean_content = content.strip()
        if not clean_content:
            return

        try:
            embedder = get_embedding_service()
            embedding, _ = embedder.embed_texts([clean_content])
            collection = self._get_collection(conversation_id)
            collection.upsert(
                ids=[message_id],
                documents=[clean_content],
                embeddings=embedding,
                metadatas=[{"role": role, "conversation_id": conversation_id}],
            )
            logger.info(
                "Indexed message to conversation memory",
                conversation_id=conversation_id,
                message_id=message_id,
                role=role,
            )
        except Exception as e:
            logger.warning(
                "Failed to index message to ChromaDB",
                conversation_id=conversation_id,
                message_id=message_id,
                error=str(e),
            )

    def add_multimodal_artifact_memory(
        self,
        conversation_id: str,
        artifact_id: str,
        content: str,
        metadata: dict[str, Any],
    ) -> None:
        """Index multimodal artifact text (transcript segment, caption, OCR) into ChromaDB."""
        clean_content = content.strip()
        if not clean_content:
            return

        try:
            embedder = get_embedding_service()
            embedding, _ = embedder.embed_texts([clean_content])
            collection = self._get_collection(conversation_id)
            meta = {
                "conversation_id": conversation_id,
                "attachment_id": str(metadata.get("attachment_id", "")),
                "type": str(metadata.get("type", "artifact")),
                "timestamps": str(metadata.get("timestamps", "")),
                "file_name": str(metadata.get("file_name", "")),
            }
            collection.upsert(
                ids=[artifact_id],
                documents=[clean_content],
                embeddings=embedding,
                metadatas=[meta],
            )
            logger.info(
                "Indexed multimodal artifact to conversation memory",
                conversation_id=conversation_id,
                artifact_id=artifact_id,
                type=meta["type"],
            )
        except Exception as e:
            logger.warning(
                "Failed to index multimodal artifact to ChromaDB",
                conversation_id=conversation_id,
                artifact_id=artifact_id,
                error=str(e),
            )

    def delete_conversation_memory(self, conversation_id: str) -> None:
        """Purge ChromaDB collection for a deleted conversation."""
        col_name = self._sanitize_collection_name(conversation_id)
        try:
            self.chroma_client.delete_collection(name=col_name)
            logger.info("Deleted ChromaDB memory collection", conversation_id=conversation_id)
        except Exception:
            # Idempotent ignore if collection does not exist
            pass

    def retrieve_memories(
        self,
        conversation_id: str,
        query: str,
        top_k: int | None = None,
        exclude_message_ids: set[str] | None = None,
    ) -> list[str]:
        """Retrieve top-K semantically relevant past turns and multimodal artifacts from ChromaDB."""
        k = top_k or settings.MEMORY_TOP_K
        clean_query = query.strip()
        if not clean_query:
            return []

        try:
            embedder = get_embedding_service()
            query_vector, _ = embedder.embed_query(clean_query)
            col_name = self._sanitize_collection_name(conversation_id)

            # Check if collection exists
            existing_cols = [c.name for c in self.chroma_client.list_collections()]
            if col_name not in existing_cols:
                return []

            collection = self._get_collection(conversation_id)
            if collection.count() == 0:
                return []

            results = collection.query(
                query_embeddings=[query_vector],
                n_results=min(k, collection.count()),
            )

            retrieved: list[str] = []
            docs = results.get("documents", [[]])[0]
            ids = results.get("ids", [[]])[0]
            metas = results.get("metadatas", [[]])[0]

            for doc_id, doc, meta in zip(ids, docs, metas):
                if exclude_message_ids and doc_id in exclude_message_ids:
                    continue
                meta_type = meta.get("type")
                if meta_type == "transcript_segment":
                    file_name = meta.get("file_name", "audio")
                    timestamps = meta.get("timestamps", "")
                    retrieved.append(f'[AUDIO file="{file_name}" t="{timestamps}"]: {doc}')
                elif meta_type == "image_caption":
                    file_name = meta.get("file_name", "image")
                    retrieved.append(f'[IMAGE file="{file_name}"]: {doc}')
                elif meta_type == "image_ocr":
                    file_name = meta.get("file_name", "image")
                    retrieved.append(f'[IMAGE OCR file="{file_name}"]: {doc}')
                else:
                    role = meta.get("role", "assistant")
                    retrieved.append(f"[{role.upper()}]: {doc}")

            return retrieved
        except Exception as e:
            logger.warning(
                "Error retrieving memories from ChromaDB",
                conversation_id=conversation_id,
                error=str(e),
            )
            return []

    def find_relevant_attachments(
        self,
        conversation_id: str,
        query: str,
        top_k: int = 5,
        type_prefix: str | None = None,
    ) -> list[dict[str, Any]]:
        """Find past attachments and their metadata matching a semantic search query."""
        clean_query = query.strip()
        if not clean_query:
            return []

        try:
            embedder = get_embedding_service()
            query_vector, _ = embedder.embed_query(clean_query)
            col_name = self._sanitize_collection_name(conversation_id)

            existing_cols = [c.name for c in self.chroma_client.list_collections()]
            if col_name not in existing_cols:
                return []

            collection = self._get_collection(conversation_id)
            if collection.count() == 0:
                return []

            results = collection.query(
                query_embeddings=[query_vector],
                n_results=min(top_k * 2, collection.count()),
            )

            metas = results.get("metadatas", [[]])[0]
            matched: list[dict[str, Any]] = []
            seen_attachments: set[str] = set()

            for meta in metas:
                att_id = meta.get("attachment_id")
                mtype = meta.get("type", "")
                if not att_id or att_id in seen_attachments:
                    continue
                if type_prefix and not mtype.startswith(type_prefix):
                    continue
                seen_attachments.add(att_id)
                matched.append(meta)
                if len(matched) >= top_k:
                    break

            return matched
        except Exception as e:
            logger.warning(
                "Error finding relevant attachments from ChromaDB",
                conversation_id=conversation_id,
                error=str(e),
            )
            return []

    def update_summary_if_needed(
        self,
        conversation: Conversation,
        all_messages: list[Message],
        short_term_ids: set[str],
        db: Session,
    ) -> None:
        """Generate/update rolling summary if older messages outside short-term window exist."""
        older_messages = [m for m in all_messages if m.id not in short_term_ids]
        if not older_messages:
            return

        total_older_tokens = sum(approx_token_count(m.content) for m in older_messages)
        if total_older_tokens < 200 and conversation.summary:
            # Skip summarizing if delta is trivial and existing summary is present
            return

        formatted_turns = "\n".join(f"{m.role.upper()}: {m.content[:400]}" for m in older_messages)

        prompt = (
            "You are a rolling conversation summarizer. Update the existing summary by incorporating "
            "the provided older turns. Preserve all crucial facts, decisions, and context concisely.\n\n"
            f"Existing Summary:\n<<<EXISTING_SUMMARY>>>\n{conversation.summary or 'None'}\n<<<EXISTING_SUMMARY>>>\n\n"
            f"Older Turns to Incorporate:\n<<<CONVERSATION_TURNS>>>\n{formatted_turns}\n<<<CONVERSATION_TURNS>>>\n\n"
            "Respond ONLY with the updated concise summary text."
        )

        try:
            llm = get_llm_service()
            new_summary, _ = llm.generate([{"role": "user", "content": prompt}], max_tokens=300)
            clean_summary = new_summary.strip()
            if clean_summary:
                conversation.summary = clean_summary
                db.add(conversation)
                db.commit()
                db.refresh(conversation)
                logger.info("Updated rolling conversation summary", conversation_id=conversation.id)
        except Exception as e:
            logger.warning(
                "Failed to update conversation summary",
                conversation_id=conversation.id,
                error=str(e),
            )

    def build_context(
        self,
        conversation_id: str,
        new_message: str,
        db: Session,
    ) -> list[dict[str, str]]:
        """Construct the LLM context prompt combining 3 tiers:

        Tier 1: Short-term token-budgeted message window
        Tier 2: Rolling conversation summary
        Tier 3: Long-term retrieved memories from ChromaDB
        All wrapped in delimited blocks for prompt hygiene.
        """
        # Fetch conversation record
        conv = db.execute(
            select(Conversation).where(Conversation.id == conversation_id)
        ).scalar_one_or_none()

        # Fetch all messages chronologically
        messages = (
            db.execute(
                select(Message)
                .where(Message.conversation_id == conversation_id)
                .order_by(Message.created_at.asc())
            )
            .scalars()
            .all()
        )

        # 1. Calculate short-term window within token budget (working backwards)
        budget = settings.MEMORY_TOKEN_BUDGET
        short_term_messages: list[Message] = []
        accumulated_tokens = approx_token_count(new_message)

        for msg in reversed(messages):
            msg_tokens = approx_token_count(msg.content)
            if accumulated_tokens + msg_tokens > budget:
                break
            short_term_messages.insert(0, msg)
            accumulated_tokens += msg_tokens

        short_term_ids = {m.id for m in short_term_messages}

        # 2. Check and trigger rolling summary if history overflowed
        if conv and len(messages) > len(short_term_messages):
            self.update_summary_if_needed(conv, list(messages), short_term_ids, db)

        # 3. Reference resolution and long-term memory retrieval
        history_for_rewriter = [{"role": m.role, "content": m.content} for m in short_term_messages]
        search_query = rewrite_query_if_needed(new_message, history_for_rewriter)

        retrieved_memories = self.retrieve_memories(
            conversation_id=conversation_id,
            query=search_query,
            top_k=settings.MEMORY_TOP_K,
            exclude_message_ids=short_term_ids,
        )

        # 4. Construct prompt elements with strict delimited blocks
        system_sections = [settings.DEFAULT_SYSTEM_PROMPT]

        if conv and conv.summary:
            system_sections.append(
                "CONVERSATION SUMMARY OF EARLIER TURNS:\n"
                "<<<CONVERSATION_SUMMARY>>>\n"
                f"{conv.summary}\n"
                "<<<CONVERSATION_SUMMARY>>>"
            )

        if retrieved_memories:
            mem_text = "\n\n".join(retrieved_memories)
            system_sections.append(
                "RELEVANT RETRIEVED CONTEXT FROM EARLIER CONVERSATION:\n"
                "<<<RETRIEVED_MEMORY>>>\n"
                f"{mem_text}\n"
                "<<<RETRIEVED_MEMORY>>>"
            )

        full_system_prompt = "\n\n".join(system_sections)

        context_messages: list[dict[str, str]] = [{"role": "system", "content": full_system_prompt}]

        # Add short-term conversation window
        for msg in short_term_messages:
            context_messages.append({"role": msg.role, "content": msg.content})

        # Add untrusted new user message enclosed in delimiter
        context_messages.append(
            {
                "role": "user",
                "content": f"<<<USER_CONTENT>>>\n{new_message}\n<<<USER_CONTENT>>>",
            }
        )

        return context_messages


def get_memory_service() -> MemoryService:
    """Retrieve singleton MemoryService instance."""
    return MemoryService.get_instance()
