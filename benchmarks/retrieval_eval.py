"""Evaluation benchmark for cross-modal and cross-lingual semantic retrieval in Knowledge Vault."""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path
from typing import Any

# Ensure UTF-8 output encoding on Windows terminals
if sys.platform == "win32":
    import io

    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

# Ensure backend root is on sys.path
backend_path = Path(__file__).resolve().parent.parent / "backend"
if str(backend_path) not in sys.path:
    sys.path.insert(0, str(backend_path))

from app.core.config import settings
from app.core.logging import setup_logging
from app.services.search_service import SearchService

setup_logging()

# Output directory
RESULTS_DIR = Path(__file__).resolve().parent / "results"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)


LABELLED_DATASET: list[dict[str, Any]] = [
    # -------------------------------------------------------------------------
    # Text items (English, Hindi, Tamil)
    # -------------------------------------------------------------------------
    {
        "id": "item_en_01",
        "modality": "text",
        "text": "The quarterly financial report confirms a 24 percent increase in recurring subscription revenue.",
        "language": "en",
        "queries": [
            ("recurring subscription revenue growth quarterly", "text_to_text"),
            ("quarterly financial report 24 percent", "text_to_text"),
        ],
    },
    {
        "id": "item_en_02",
        "modality": "text",
        "text": "Engineering deployment schedule: Kubernetes microservices cluster upgrade planned for Sunday midnight.",
        "language": "en",
        "queries": [
            ("kubernetes cluster upgrade schedule", "text_to_text"),
        ],
    },
    {
        "id": "item_en_03",
        "modality": "audio",
        "text": "Meeting transcript: Alice approved the marketing budget of fifty thousand dollars for Q3.",
        "language": "en",
        "queries": [
            ("marketing budget fifty thousand dollars Q3", "text_to_text"),
            ("Alice approved marketing budget", "text_to_text"),
        ],
    },
    {
        "id": "item_en_04",
        "modality": "text",
        "text": "Security incident postmortem: unauthorized API key rotation detected and revoked immediately.",
        "language": "en",
        "queries": [
            ("unauthorized API key rotation security postmortem", "text_to_text"),
        ],
    },
    {
        "id": "item_en_05",
        "modality": "audio",
        "text": "Product roadmap sync: mobile app biometric login and offline sync scheduled for release in November.",
        "language": "en",
        "queries": [
            ("mobile biometric login offline sync release", "text_to_text"),
        ],
    },
    {
        "id": "item_en_06",
        "modality": "text",
        "text": "Database optimization guidelines: use compound indexes on user_id and created_at timestamps.",
        "language": "en",
        "queries": [
            ("database compound index user_id created_at", "text_to_text"),
        ],
    },
    {
        "id": "item_en_07",
        "modality": "audio",
        "text": "Executive sync: board agreed to open new regional development center in Bangalore.",
        "language": "en",
        "queries": [
            ("new regional development center Bangalore", "text_to_text"),
        ],
    },
    {
        "id": "item_en_08",
        "modality": "text",
        "text": "Customer feedback analysis indicates 92% user satisfaction with the updated dashboard UI.",
        "language": "en",
        "queries": [
            ("user satisfaction updated dashboard UI 92%", "text_to_text"),
        ],
    },
    {
        "id": "item_en_09",
        "modality": "audio",
        "text": "The legal department approved the vendor master service agreement with updated liability clauses.",
        "language": "en",
        "queries": [
            ("vendor master service agreement liability clauses", "text_to_text"),
        ],
    },
    {
        "id": "item_en_10",
        "modality": "text",
        "text": "Server maintenance window completed successfully with zero downtime across all production zones.",
        "language": "en",
        "queries": [
            ("server maintenance zero downtime production", "text_to_text"),
        ],
    },
    # -------------------------------------------------------------------------
    # Image items (Captions & Visuals)
    # -------------------------------------------------------------------------
    {
        "id": "item_img_01",
        "modality": "image",
        "text": "Bar chart diagram showing quarterly sales growth across North America and Europe.",
        "language": "en",
        "queries": [
            ("sales growth bar chart diagram", "text_to_image"),
            ("quarterly sales across North America", "text_to_image"),
        ],
    },
    {
        "id": "item_img_02",
        "modality": "image",
        "text": "Photograph of a red sports car parked in front of a modern glass skyscraper.",
        "language": "en",
        "queries": [
            ("red sports car skyscraper", "text_to_image"),
            ("sports car modern glass building", "text_to_image"),
        ],
    },
    {
        "id": "item_img_03",
        "modality": "image",
        "text": "Architecture diagram illustrating FastAPI microservices communicating with PostgreSQL and ChromaDB.",
        "language": "en",
        "queries": [
            ("microservices architecture diagram ChromaDB", "text_to_image"),
        ],
    },
    {
        "id": "item_img_04",
        "modality": "image",
        "text": "Whiteboard snapshot with user journey flowchart and authentication wireframes.",
        "language": "en",
        "queries": [
            ("whiteboard user journey flowchart wireframes", "text_to_image"),
        ],
    },
    {
        "id": "item_img_05",
        "modality": "image",
        "text": "Screenshot of dark mode analytics dashboard displaying latency metrics and throughput graphs.",
        "language": "en",
        "queries": [
            ("dark mode analytics dashboard latency throughput", "text_to_image"),
        ],
    },
    {
        "id": "item_img_06",
        "modality": "image",
        "text": "Infographic showing machine learning pipeline stages: ingestion, tokenization, and vector retrieval.",
        "language": "en",
        "queries": [
            ("machine learning pipeline infographic vector retrieval", "text_to_image"),
        ],
    },
    {
        "id": "item_img_07",
        "modality": "image",
        "text": "Photo of conference room with team discussing project milestones around a wooden table.",
        "language": "en",
        "queries": [
            ("team meeting conference room wooden table", "text_to_image"),
        ],
    },
    {
        "id": "item_img_08",
        "modality": "image",
        "text": "High resolution schematic diagram of robotic arm mechanical assembly.",
        "language": "en",
        "queries": [
            ("robotic arm mechanical assembly schematic", "text_to_image"),
        ],
    },
    {
        "id": "item_img_09",
        "modality": "image",
        "text": "Line chart showing CPU and GPU memory utilization over a forty-eight hour stress test.",
        "language": "en",
        "queries": [
            ("CPU GPU memory utilization chart stress test", "text_to_image"),
        ],
    },
    {
        "id": "item_img_10",
        "modality": "image",
        "text": "Product packaging mockup displaying eco-friendly recyclable materials and logo branding.",
        "language": "en",
        "queries": [
            ("eco-friendly product packaging mockup branding", "text_to_image"),
        ],
    },
    # -------------------------------------------------------------------------
    # Cross-Lingual items (Hindi & Tamil content and queries)
    # -------------------------------------------------------------------------
    {
        "id": "item_xl_01",
        "modality": "text",
        "text": "वार्षिक बजट बैठक में सभी विभागों के वित्तीय आवंटन को अंतिम रूप दिया गया।",  # Hindi: Annual budget meeting finalized financial allocation
        "language": "hi",
        "queries": [
            (
                "annual budget financial allocation meeting",
                "cross_lingual",
            ),  # English query -> Hindi doc
            ("वित्तीय आवंटन बजट", "cross_lingual"),
        ],
    },
    {
        "id": "item_xl_02",
        "modality": "text",
        "text": "புதிய மென்பொருள் பதிப்பு பயனர்களின் பாதுகாப்பை மேம்படுத்துகிறது மற்றும் பிழைகளை நீக்குகிறது.",  # Tamil: New software version improves security
        "language": "ta",
        "queries": [
            (
                "new software release user security bug fixes",
                "cross_lingual",
            ),  # English query -> Tamil doc
            ("மென்பொருள் பாதுகாப்பு", "cross_lingual"),
        ],
    },
    {
        "id": "item_xl_03",
        "modality": "text",
        "text": "Artificial intelligence research on multilingual semantic representations and neural search.",
        "language": "en",
        "queries": [
            (
                "कृत्रिम बुद्धिमत्ता बहुभाषी खोज",
                "cross_lingual",
            ),  # Hindi query -> English doc
            (
                "செயற்கை நுண்ணறிவு பலமொழி தேடல்",
                "cross_lingual",
            ),  # Tamil query -> English doc
        ],
    },
    {
        "id": "item_xl_04",
        "modality": "audio",
        "text": "परियोजना समयरेखा: नए मोबाइल एप्लिकेशन का बीटा परीक्षण अगले सप्ताह शुरू होगा।",  # Hindi: Mobile app beta testing next week
        "language": "hi",
        "queries": [
            ("mobile application beta testing timeline next week", "cross_lingual"),
        ],
    },
    {
        "id": "item_xl_05",
        "modality": "audio",
        "text": "நிறுவனத்தின் மூன்றாம் காலாண்டு விற்பனை இலக்கு வெற்றிகரமாக எட்டப்பட்டது.",  # Tamil: Q3 sales target achieved
        "language": "ta",
        "queries": [
            ("third quarter sales target successfully achieved", "cross_lingual"),
        ],
    },
    {
        "id": "item_xl_06",
        "modality": "text",
        "text": "Renewable energy solar panel installation project completed for the main headquarters.",
        "language": "en",
        "queries": [
            (
                "सौर ऊर्जा पैनल स्थापना मुख्यालय",
                "cross_lingual",
            ),  # Hindi query -> English doc
            (
                "சூரிய மின்சக்தி திட்டம் தலைமையகம்",
                "cross_lingual",
            ),  # Tamil query -> English doc
        ],
    },
    {
        "id": "item_xl_07",
        "modality": "image",
        "text": "Diagram showing solar power grid integration with energy storage battery systems.",
        "language": "en",
        "queries": [
            (
                "सौर ऊर्जा ग्रिड बैटरी आरेख",
                "cross_lingual",
            ),  # Hindi query -> English image
        ],
    },
    {
        "id": "item_xl_08",
        "modality": "text",
        "text": "மருத்துவ ஆராய்ச்சி அறிக்கை புதிய சிகிச்சை முறையின் வெற்றிகரமான முடிவுகளை உறுதிப்படுத்துகிறது.",  # Tamil: Clinical research confirms treatment success
        "language": "ta",
        "queries": [
            ("clinical research treatment successful outcomes report", "cross_lingual"),
        ],
    },
    {
        "id": "item_xl_09",
        "modality": "text",
        "text": "डाटा सेंटर सुरक्षा प्रोटोकॉल: बायोमेट्रिक सत्यापन और चौबीसों घंटे निगरानी अनिवार्य है।",  # Hindi: Data center security protocol
        "language": "hi",
        "queries": [
            (
                "data center security biometric verification surveillance",
                "cross_lingual",
            ),
        ],
    },
    {
        "id": "item_xl_10",
        "modality": "text",
        "text": "Supply chain logistics optimization: automated warehouse inventory tracking implemented.",
        "language": "en",
        "queries": [
            (
                "आपूर्ति श्रृंखला रसद सूची स्वचालन",
                "cross_lingual",
            ),  # Hindi query -> English doc
        ],
    },
]


def run_evaluation() -> dict[str, Any]:
    """Execute evaluation benchmark and compute Recall@1, Recall@5, Recall@10, and MRR."""
    eval_user_id = "bench_eval_user_001"
    search_service = SearchService.get_instance()

    print("\n" + "=" * 60)
    print(f"KNOWLEDGE VAULT RETRIEVAL BENCHMARK (MOCK: {settings.MOCK_MODELS})")
    print("=" * 60)

    # 1. Index labelled dataset into Knowledge Vault
    print(
        f"\n[+] Indexing {len(LABELLED_DATASET)} multimodal & multilingual test items..."
    )
    for item in LABELLED_DATASET:
        item_id = item["id"]
        modality = item["modality"]
        text = item["text"]
        lang = item["language"]

        if modality == "audio":
            search_service.index_transcript(
                user_id=eval_user_id,
                conversation_id="conv_eval",
                attachment_id=item_id,
                transcript_data={
                    "text": text,
                    "language": lang,
                    "segments": [{"start": 0.0, "end": 10.0, "text": text}],
                },
            )
        elif modality == "image":
            search_service.index_image_analysis(
                user_id=eval_user_id,
                conversation_id="conv_eval",
                attachment_id=item_id,
                analysis_data={"caption": text, "ocr_text": ""},
                image_path=None,
            )
        else:
            search_service.index_message(
                user_id=eval_user_id,
                conversation_id="conv_eval",
                message_id=item_id,
                content=text,
                role="user",
                language=lang,
            )

    print("[OK] Dataset successfully indexed into Knowledge Vault.")

    # 2. Run queries and compute metrics
    category_metrics: dict[str, dict[str, float]] = {
        "text_to_text": {"queries": 0, "r1": 0, "r5": 0, "r10": 0, "mrr_sum": 0.0},
        "text_to_image": {"queries": 0, "r1": 0, "r5": 0, "r10": 0, "mrr_sum": 0.0},
        "cross_lingual": {"queries": 0, "r1": 0, "r5": 0, "r10": 0, "mrr_sum": 0.0},
        "overall": {"queries": 0, "r1": 0, "r5": 0, "r10": 0, "mrr_sum": 0.0},
    }

    detailed_rows: list[dict[str, Any]] = []

    print("\n[+] Evaluating retrieval queries...")
    for item in LABELLED_DATASET:
        target_id = item["id"]
        for query_text, category in item["queries"]:
            results = search_service.search_vault(
                query=query_text,
                user_id=eval_user_id,
                top_k=10,
            )

            # Determine rank of target item in results
            rank: int | None = None
            for idx, res in enumerate(results):
                # Target matches if id matches or attachment_id matches
                if (
                    res.id == target_id
                    or res.attachment_id == target_id
                    or target_id in res.id
                ):
                    rank = idx + 1
                    break

            r1 = 1 if rank == 1 else 0
            r5 = 1 if (rank is not None and rank <= 5) else 0
            r10 = 1 if (rank is not None and rank <= 10) else 0
            reciprocal_rank = (1.0 / rank) if rank else 0.0

            # Update category counts
            for cat in (category, "overall"):
                category_metrics[cat]["queries"] += 1
                category_metrics[cat]["r1"] += r1
                category_metrics[cat]["r5"] += r5
                category_metrics[cat]["r10"] += r10
                category_metrics[cat]["mrr_sum"] += reciprocal_rank

            detailed_rows.append(
                {
                    "query": query_text,
                    "target_id": target_id,
                    "category": category,
                    "rank": rank if rank else "Not Found",
                    "r1": r1,
                    "r5": r5,
                    "r10": r10,
                    "mrr": round(reciprocal_rank, 4),
                }
            )

    # 3. Aggregate final scores
    summary_results: dict[str, dict[str, float]] = {}
    for cat, vals in category_metrics.items():
        q_count = vals["queries"] or 1
        summary_results[cat] = {
            "query_count": float(vals["queries"]),
            "recall_at_1": round(vals["r1"] / q_count, 4),
            "recall_at_5": round(vals["r5"] / q_count, 4),
            "recall_at_10": round(vals["r10"] / q_count, 4),
            "mrr": round(vals["mrr_sum"] / q_count, 4),
        }

    # 4. Write CSV results
    csv_path = RESULTS_DIR / "retrieval_eval.csv"
    with open(csv_path, mode="w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "query",
                "target_id",
                "category",
                "rank",
                "r1",
                "r5",
                "r10",
                "mrr",
            ],
        )
        writer.writeheader()
        writer.writerows(detailed_rows)

    # 5. Write JSON results
    json_path = RESULTS_DIR / "retrieval_eval.json"
    with open(json_path, mode="w", encoding="utf-8") as f:
        json.dump(
            {
                "mock_mode": settings.MOCK_MODELS,
                "profile": settings.PROFILE,
                "summary": summary_results,
                "details": detailed_rows,
            },
            f,
            indent=2,
            ensure_ascii=False,
        )

    # 6. Write Markdown table
    md_path = RESULTS_DIR / "retrieval_eval.md"
    md_content = [
        "# Knowledge Vault Retrieval Benchmark Results\n",
        f"- **Mock Models**: `{settings.MOCK_MODELS}`",
        f"- **Profile**: `{settings.PROFILE}`",
        f"- **Total Queries Evaluated**: `{int(summary_results['overall']['query_count'])}`\n",
        "## Summary Metrics\n",
        "| Evaluation Category | Queries | Recall@1 | Recall@5 | Recall@10 | MRR |",
        "| :--- | :--- | :--- | :--- | :--- | :--- |",
    ]
    for cat, stats in summary_results.items():
        md_content.append(
            f"| **{cat}** | {int(stats['query_count'])} | {stats['recall_at_1']:.4f} | "
            f"{stats['recall_at_5']:.4f} | {stats['recall_at_10']:.4f} | {stats['mrr']:.4f} |"
        )

    with open(md_path, mode="w", encoding="utf-8") as f:
        f.write("\n".join(md_content) + "\n")

    print(
        f"\n[OK] Results successfully exported to:\n    - {csv_path}\n    - {json_path}\n    - {md_path}"
    )
    print("\n" + "\n".join(md_content[4:]))
    print("=" * 60 + "\n")

    return summary_results


if __name__ == "__main__":
    run_evaluation()
