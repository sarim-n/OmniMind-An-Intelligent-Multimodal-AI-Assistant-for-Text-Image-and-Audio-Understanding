"""Unit tests for conversation memory, ChromaDB indexing, embeddings, and query rewriting."""

from sqlalchemy.orm import Session

from app.models.conversation import Conversation
from app.models.message import Message
from app.models.user import User
from app.services.embedding_service import get_embedding_service
from app.services.memory_service import get_memory_service
from app.services.query_rewriter import has_conversational_reference, rewrite_query_if_needed


def test_embedding_service_dimensions_and_prefixes() -> None:
    service = get_embedding_service()
    # Test batch embedding
    embeddings, timing = service.embed_texts(["First document", "Second document"])
    assert len(embeddings) == 2
    assert len(embeddings[0]) == service.dim
    assert timing >= 0

    # Test query embedding
    query_vec, q_timing = service.embed_query("Search query")
    assert len(query_vec) == service.dim
    assert q_timing >= 0


def test_reference_detection() -> None:
    assert has_conversational_reference("What about it?") is True
    assert has_conversational_reference("Explain the second one") is True
    assert has_conversational_reference("tell me more") is True
    assert has_conversational_reference("How does PyTorch handle tensors?") is False


def test_query_rewriter_no_reference_returns_original() -> None:
    query = "What is the capital of Japan?"
    rewritten = rewrite_query_if_needed(query, history=[])
    assert rewritten == query


def test_query_rewriter_with_reference() -> None:
    history = [
        {"role": "user", "content": "Tell me about quantum computers."},
        {"role": "assistant", "content": "Quantum computers use qubits to compute."},
    ]
    query = "How much does it cost?"
    rewritten = rewrite_query_if_needed(query, history=history)
    assert isinstance(rewritten, str)
    assert len(rewritten) > 0


def test_chroma_memory_lifecycle(db: Session, test_user: User) -> None:
    mem_service = get_memory_service()

    # 1. Create a test conversation
    conv = Conversation(user_id=test_user.id, title="Memory Test")
    db.add(conv)
    db.commit()
    db.refresh(conv)

    # 2. Add message memories
    msg1 = Message(
        conversation_id=conv.id,
        role="user",
        content="My favorite framework is FastAPI because of async speed.",
    )
    db.add(msg1)
    db.commit()
    db.refresh(msg1)

    mem_service.add_message_memory(conv.id, msg1.id, msg1.content, "user")

    # 3. Retrieve memory
    retrieved = mem_service.retrieve_memories(
        conversation_id=conv.id,
        query="What framework was mentioned?",
        top_k=2,
    )
    assert isinstance(retrieved, list)

    # 4. Clean up / delete memory
    mem_service.delete_conversation_memory(conv.id)


def test_build_context_with_prompt_hygiene(db: Session, test_user: User) -> None:
    mem_service = get_memory_service()

    conv = Conversation(user_id=test_user.id, title="Prompt Test")
    db.add(conv)
    db.commit()
    db.refresh(conv)

    # Add historical turns
    msg1 = Message(conversation_id=conv.id, role="user", content="Hello OmniMind")
    msg2 = Message(
        conversation_id=conv.id, role="assistant", content="Hello! How can I assist you?"
    )
    db.add_all([msg1, msg2])
    db.commit()

    context = mem_service.build_context(conv.id, "Tell me a story", db)

    # Verify context structure
    assert len(context) >= 3
    system_turn = context[0]
    assert system_turn["role"] == "system"
    assert "CRITICAL SECURITY INSTRUCTION" in system_turn["content"]

    last_user_turn = context[-1]
    assert last_user_turn["role"] == "user"
    assert "<<<USER_CONTENT>>>" in last_user_turn["content"]
    assert "Tell me a story" in last_user_turn["content"]


def test_token_budget_overflow_triggers_summary(db: Session, test_user: User) -> None:
    mem_service = get_memory_service()

    conv = Conversation(user_id=test_user.id, title="Budget Test")
    db.add(conv)
    db.commit()
    db.refresh(conv)

    # Populate 20 messages with long text to exceed the token budget
    for i in range(20):
        m = Message(
            conversation_id=conv.id,
            role="user" if i % 2 == 0 else "assistant",
            content=f"Message turn number {i}: " + ("detailed context description " * 30),
        )
        db.add(m)
    db.commit()

    # Build context which executes summary compaction for overflow turns
    context = mem_service.build_context(conv.id, "New follow up question", db)
    assert len(context) > 0

    # Verify conversation summary was updated
    db.refresh(conv)
    assert conv.summary is not None
    assert len(conv.summary) > 0
