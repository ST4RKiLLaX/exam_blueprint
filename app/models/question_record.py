from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Dict, List, Optional

from app.models.user import db


class QuestionRecord(db.Model):
    """Persisted generated question with retrieval and difficulty metadata."""

    __tablename__ = "question_records"

    id = db.Column(db.Integer, primary_key=True)
    created_at = db.Column(db.DateTime(), default=datetime.utcnow, nullable=False, index=True)
    updated_at = db.Column(
        db.DateTime(), default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    # Lifecycle
    status = db.Column(db.String(32), default="active", nullable=False)
    is_deleted = db.Column(db.Boolean(), default=False, nullable=False, index=True)

    # Content
    question_text = db.Column(db.Text, nullable=False)
    answer_text = db.Column(db.Text, nullable=True)
    explanation = db.Column(db.Text, nullable=True)
    options_json = db.Column(db.Text, nullable=True)  # JSON list[str|dict]

    # Ownership / context
    user_id = db.Column(db.Integer, nullable=True, index=True)
    agent_id = db.Column(db.String(128), nullable=True, index=True)
    session_id = db.Column(db.String(128), nullable=True, index=True)
    exam_profile_id = db.Column(db.String(128), nullable=True, index=True)

    # Filtering metadata
    domain = db.Column(db.String(128), nullable=True, index=True)
    difficulty_level_id = db.Column(db.String(64), nullable=True, index=True)
    difficulty_display_name = db.Column(db.String(128), nullable=True)
    question_type_id = db.Column(db.String(128), nullable=True)
    question_type_phrase = db.Column(db.String(256), nullable=True)
    topics_json = db.Column(db.Text, nullable=True)  # JSON list[str]

    # Retrieval metadata
    hot_topics_mode_effective = db.Column(db.String(32), nullable=True)
    hot_topics_used = db.Column(db.Boolean(), nullable=True)
    retrieval_path = db.Column(db.String(64), nullable=True)

    # Trace metadata
    source_type = db.Column(db.String(32), default="chat", nullable=False)
    provider = db.Column(db.String(64), nullable=True)
    provider_model = db.Column(db.String(128), nullable=True)

    __table_args__ = (
        db.Index("idx_question_domain_difficulty", "domain", "difficulty_level_id"),
    )

    @staticmethod
    def _loads_list(raw_value: Optional[str]) -> List[str]:
        if not raw_value:
            return []
        try:
            parsed = json.loads(raw_value)
            if isinstance(parsed, list):
                return [str(item) for item in parsed if str(item).strip()]
        except Exception:
            return []
        return []

    @staticmethod
    def _dumps_list(raw_value: Any) -> Optional[str]:
        if raw_value is None:
            return None
        if isinstance(raw_value, list):
            cleaned = [str(item).strip() for item in raw_value if str(item).strip()]
            return json.dumps(cleaned, ensure_ascii=False)
        if isinstance(raw_value, str):
            value = raw_value.strip()
            if not value:
                return json.dumps([], ensure_ascii=False)
            try:
                parsed = json.loads(value)
                if isinstance(parsed, list):
                    cleaned = [str(item).strip() for item in parsed if str(item).strip()]
                    return json.dumps(cleaned, ensure_ascii=False)
            except Exception:
                cleaned = [item.strip() for item in value.split(",") if item.strip()]
                return json.dumps(cleaned, ensure_ascii=False)
        return json.dumps([], ensure_ascii=False)

    def set_topics(self, topics: Any) -> None:
        self.topics_json = self._dumps_list(topics)

    def get_topics(self) -> List[str]:
        return self._loads_list(self.topics_json)

    def set_options(self, options: Any) -> None:
        if options is None:
            self.options_json = None
            return

        payload = options
        if isinstance(options, str):
            value = options.strip()
            if not value:
                payload = []
            else:
                try:
                    payload = json.loads(value)
                except Exception:
                    payload = [item.strip() for item in value.splitlines() if item.strip()]

        if isinstance(payload, list):
            cleaned = []
            for item in payload:
                if isinstance(item, dict):
                    text = str(item.get("text", "")).strip()
                    if not text:
                        continue
                    normalized = {
                        "text": text,
                        "is_correct": bool(item.get("is_correct", False)),
                    }
                    label = str(item.get("label", "")).strip()
                    if label:
                        normalized["label"] = label
                    cleaned.append(normalized)
                elif isinstance(item, str):
                    text = item.strip()
                    if text:
                        cleaned.append(text)
            self.options_json = json.dumps(cleaned, ensure_ascii=False)
            return

        self.options_json = json.dumps([], ensure_ascii=False)

    def get_options(self) -> List[Any]:
        if not self.options_json:
            return []
        try:
            parsed = json.loads(self.options_json)
            if isinstance(parsed, list):
                return parsed
        except Exception:
            return []
        return []

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "status": self.status,
            "is_deleted": self.is_deleted,
            "question_text": self.question_text,
            "answer_text": self.answer_text,
            "explanation": self.explanation,
            "options": self.get_options(),
            "topics": self.get_topics(),
            "user_id": self.user_id,
            "agent_id": self.agent_id,
            "session_id": self.session_id,
            "exam_profile_id": self.exam_profile_id,
            "domain": self.domain,
            "difficulty_level_id": self.difficulty_level_id,
            "difficulty_display_name": self.difficulty_display_name,
            "question_type_id": self.question_type_id,
            "question_type_phrase": self.question_type_phrase,
            "hot_topics_mode_effective": self.hot_topics_mode_effective,
            "hot_topics_used": self.hot_topics_used,
            "retrieval_path": self.retrieval_path,
            "source_type": self.source_type,
            "provider": self.provider,
            "provider_model": self.provider_model,
        }
