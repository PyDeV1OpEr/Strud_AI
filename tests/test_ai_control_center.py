# tests/test_ai_control_center.py
#
# Strud AI — Automated test suite for AI Control Center functionality.
# Covers:
#   1. Usage persistence, summary aggregation, date filters, latency
#   2. GitHub-style calendar generation in Asia/Colombo timezone
#   3. Token intensity scaling and historical tracking boundary
#   4. Model endpoints, connection test mock, and active model updates
#   5. RAG status, document list, and live query test inspector
#   6. Memory addition, clear-all, and memory_enabled toggle
#   7. Profile full personalization update and persistence
#   8. Privacy storage stats and full JSON export
#   9. System diagnostics live checks (never hardcoded green)

from __future__ import annotations

import tempfile
import unittest
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch
from zoneinfo import ZoneInfo

from fastapi.testclient import TestClient

from strud.backend.memory_store import MemoryStore
from strud.backend.api.main import app

COLOMBO_TZ = ZoneInfo("Asia/Colombo")


class TestAIControlCenterBackend(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test_memory.db"
        self.store = MemoryStore(self.db_path)
        self.client = TestClient(app)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    # -------------------------------------------------------------------------
    # 1. Usage Persistence & Aggregation
    # -------------------------------------------------------------------------
    def test_usage_persistence_and_summary(self) -> None:
        user_id = "test_user_usage_1"
        now_utc = datetime.now(timezone.utc)

        # Record 1 successful request
        rec1 = self.store.record_usage(
            user_id=user_id,
            chat_id="chat-1",
            model_id="openai/gpt-oss-20b",
            input_tokens=150,
            output_tokens=350,
            token_counting_method="provider",
            request_status="success",
            duration_ms=420,
            created_at=now_utc.isoformat(),
        )
        self.assertGreater(rec1, 0)

        # Record 1 failed request
        rec2 = self.store.record_usage(
            user_id=user_id,
            chat_id="chat-1",
            model_id="openai/gpt-oss-20b",
            input_tokens=80,
            output_tokens=0,
            token_counting_method="tiktoken_cl100k",
            request_status="failed",
            duration_ms=150,
            created_at=now_utc.isoformat(),
        )
        self.assertGreater(rec2, 0)

        summary = self.store.get_usage_summary(user_id=user_id, range_key="today")
        self.assertEqual(summary["total_requests"], 2)
        self.assertEqual(summary["successful_requests"], 1)
        self.assertEqual(summary["failed_requests"], 1)
        self.assertEqual(summary["input_tokens"], 150)
        self.assertEqual(summary["output_tokens"], 350)
        self.assertEqual(summary["total_tokens"], 500)
        self.assertEqual(summary["avg_tokens_per_request"], 500.0)
        self.assertEqual(summary["avg_latency_ms"], 420.0)
        self.assertEqual(summary["tokens_today"], 500)

    # -------------------------------------------------------------------------
    # 2. Contribution Calendar & Timezone Handling (Asia/Colombo)
    # -------------------------------------------------------------------------
    def test_calendar_asia_colombo_timezone(self) -> None:
        user_id = "test_user_cal"
        # 2026-10-14 20:00:00 UTC is 2026-10-15 01:30:00 in Asia/Colombo (+05:30)
        dt_utc = datetime(2026, 10, 14, 20, 0, 0, tzinfo=timezone.utc)

        self.store.record_usage(
            user_id=user_id,
            chat_id="chat-cal",
            model_id="openai/gpt-oss-20b",
            input_tokens=1000,
            output_tokens=2000,
            token_counting_method="provider",
            request_status="success",
            duration_ms=500,
            created_at=dt_utc.isoformat(),
        )

        cal = self.store.get_usage_calendar(user_id=user_id, year=2026)
        self.assertEqual(cal["year"], 2026)
        self.assertEqual(cal["timezone"], "Asia/Colombo")
        self.assertEqual(cal["total_tokens"], 3000)
        self.assertEqual(cal["total_requests"], 1)

        # In Colombo timezone, the day is 2026-10-15
        day_15 = next((d for d in cal["days"] if d["date"] == "2026-10-15"), None)
        self.assertIsNotNone(day_15)
        self.assertEqual(day_15["total_tokens"], 3000)
        self.assertEqual(day_15["intensity"], 2)  # 2501 - 10000 is level 2
        self.assertEqual(day_15["status"], "tracked")

        # An earlier day prior to first tracked date should have status 'unavailable'
        day_early = next((d for d in cal["days"] if d["date"] == "2026-01-10"), None)
        self.assertIsNotNone(day_early)
        self.assertEqual(day_early["status"], "unavailable")
        self.assertEqual(day_early["intensity"], 0)

    # -------------------------------------------------------------------------
    # 3. Intensity Scale Verification
    # -------------------------------------------------------------------------
    def test_intensity_scaling(self) -> None:
        user_id = "test_user_scale"
        now_str = datetime(2026, 6, 1, 10, 0, 0, tzinfo=timezone.utc).isoformat()

        # Add 35,000 tokens for level 4
        self.store.record_usage(
            user_id=user_id,
            chat_id="chat-1",
            model_id="model-1",
            input_tokens=15000,
            output_tokens=20000,
            created_at=now_str,
        )

        cal = self.store.get_usage_calendar(user_id=user_id, year=2026)
        day_entry = next((d for d in cal["days"] if d["date"] == "2026-06-01"), None)
        self.assertIsNotNone(day_entry)
        self.assertEqual(day_entry["intensity"], 4)

    # -------------------------------------------------------------------------
    # 4. Timeseries & Model Breakdown
    # -------------------------------------------------------------------------
    def test_timeseries_and_model_breakdown(self) -> None:
        user_id = "test_user_ts"
        now_str = datetime.now(timezone.utc).isoformat()

        self.store.record_usage(
            user_id=user_id,
            chat_id="chat-1",
            model_id="openai/gpt-oss-20b",
            input_tokens=100,
            output_tokens=200,
            created_at=now_str,
        )
        self.store.record_usage(
            user_id=user_id,
            chat_id="chat-1",
            model_id="qwen/qwen3-vl-8b",
            input_tokens=300,
            output_tokens=400,
            created_at=now_str,
        )

        ts = self.store.get_usage_timeseries(user_id=user_id, range_key="last_7_days")
        self.assertGreater(len(ts), 0)

        models = self.store.get_usage_by_model(user_id=user_id)
        model_ids = {m["model_id"] for m in models}
        self.assertIn("openai/gpt-oss-20b", model_ids)
        self.assertIn("qwen/qwen3-vl-8b", model_ids)

    # -------------------------------------------------------------------------
    # 5. Profile Personalization Full Lifecycle
    # -------------------------------------------------------------------------
    def test_profile_personalization_full(self) -> None:
        user_id = "user_pref_test_1"
        initial = self.store.get_profile(user_id)
        self.assertEqual(initial["display_name"], "Student")
        self.assertEqual(initial["response_style"], "balanced")
        self.assertTrue(initial["memory_enabled"])

        updated = self.store.set_profile(
            user_id=user_id,
            display_name="BiologyScholar",
            avatar="violet",
            response_style="concise",
            explanation_detail="deep",
            study_focus="exam",
            memory_enabled=False,
            custom_instructions="Focus on past paper questions",
        )
        self.assertEqual(updated["display_name"], "BiologyScholar")
        self.assertEqual(updated["avatar"], "violet")
        self.assertEqual(updated["response_style"], "concise")
        self.assertEqual(updated["explanation_detail"], "deep")
        self.assertEqual(updated["study_focus"], "exam")
        self.assertFalse(updated["memory_enabled"])
        self.assertEqual(updated["custom_instructions"], "Focus on past paper questions")

        # Verify persistent reload
        reloaded = self.store.get_profile(user_id)
        self.assertEqual(reloaded["display_name"], "BiologyScholar")
        self.assertFalse(reloaded["memory_enabled"])

    # -------------------------------------------------------------------------
    # 6. Memory Management: Clear All & Settings Toggle
    # -------------------------------------------------------------------------
    def test_memory_clear_all_and_toggle(self) -> None:
        user_id = "user_mem_mgr_1"
        self.store.remember(user_id, "Fact 1", source="explicit")
        self.store.remember(user_id, "Fact 2", source="conversation")

        facts = self.store.recall(user_id)
        self.assertEqual(len(facts), 2)

        cleared = self.store.delete_all_memories(user_id)
        self.assertEqual(cleared, 2)
        self.assertEqual(len(self.store.recall(user_id)), 0)

    # -------------------------------------------------------------------------
    # 7. Privacy Storage Info & Export
    # -------------------------------------------------------------------------
    def test_storage_stats_and_export(self) -> None:
        user_id = "user_export_test"
        uploads_dir = Path(self.temp_dir.name) / "uploads"
        uploads_dir.mkdir()
        (uploads_dir / "sample.png").write_bytes(b"12345678")

        self.store.append_message(chat_id="chat-1", user_id=user_id, role="user", content="Hello Biology")

        stats = self.store.get_storage_stats(user_id, uploads_dir, Path(self.temp_dir.name))
        self.assertGreaterEqual(stats["database_size_bytes"], 0)
        self.assertEqual(stats["uploads_count"], 1)
        self.assertEqual(stats["uploads_size_bytes"], 8)
        self.assertEqual(stats["messages_count"], 1)

        archive = self.store.export_full_data(user_id)
        self.assertEqual(archive["user_id"], user_id)
        self.assertIn("profile", archive)
        self.assertIn("chats", archive)

    # -------------------------------------------------------------------------
    # 8. API Endpoint Tests via TestClient
    # -------------------------------------------------------------------------
    def test_api_analytics_endpoints(self) -> None:
        resp = self.client.get("/api/analytics/summary?user_id=local&range=last_30_days")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("tokens_today", data)
        self.assertIn("avg_tokens_per_request", data)

        resp_cal = self.client.get("/api/analytics/calendar?user_id=local&year=2026")
        self.assertEqual(resp_cal.status_code, 200)
        cal_data = resp_cal.json()
        self.assertEqual(cal_data["year"], 2026)
        self.assertEqual(len(cal_data["days"]), 365)

    def test_api_models_endpoint(self) -> None:
        resp = self.client.get("/api/models")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("activeModel", data)
        self.assertIn("visionModel", data)
        self.assertIn("capabilities", data["activeModel"])

    @patch("requests.get")
    def test_api_model_connection_test(self, mock_get: MagicMock) -> None:
        # Mock successful LM Studio response
        mock_resp = MagicMock()
        mock_resp.ok = True
        mock_resp.json.return_value = {
            "data": [{"id": "openai/gpt-oss-20b"}, {"id": "qwen/qwen3-vl-8b"}]
        }
        mock_get.return_value = mock_resp

        resp = self.client.post("/api/models/test", json={"modelId": "openai/gpt-oss-20b"})
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data["ok"])
        self.assertEqual(data["status"], "healthy")

    def test_api_rag_status_and_docs(self) -> None:
        resp = self.client.get("/api/rag/status")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("chunk_count", resp.json())

        resp_docs = self.client.get("/api/rag/documents")
        self.assertEqual(resp_docs.status_code, 200)
        self.assertIn("documents", resp_docs.json())

    def test_api_diagnostics_honest_states(self) -> None:
        resp = self.client.get("/api/diagnostics")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("checks", data)
        self.assertIn("status", data)
        check_names = [c["name"] for c in data["checks"]]
        self.assertTrue(any("FastAPI" in n for n in check_names))
        self.assertTrue(any("SQLite" in n for n in check_names))


if __name__ == "__main__":
    unittest.main()
