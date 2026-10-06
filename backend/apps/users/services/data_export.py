"""
Subject Access Request (SAR) Data Export Service.
Compliant with GDPR Article 15 and POPIA Section 23.

Generates a portable, machine-readable export of all personal data held for a data subject.
Redacts internal financial liability records, payment gateway internal tokens, and internal staff notes.
"""

from __future__ import annotations

import io
import json
import uuid
import zipfile
from datetime import datetime, timezone
from typing import Any

from django.contrib.auth import get_user_model

User = get_user_model()


def _extract_profile(user: Any) -> dict[str, Any]:
    return {
        "id": str(user.id),
        "username": user.username,
        "email": user.email,
        "first_name": user.first_name,
        "last_name": user.last_name,
        "role": user.role,
        "country": user.country,
        "timezone": user.timezone,
        "phone_number": getattr(user, "phone_number", ""),
        "email_verified": getattr(user, "email_verified", False),
        "date_joined": user.date_joined.isoformat() if getattr(user, "date_joined", None) else None,
        "last_login": user.last_login.isoformat() if user.last_login else None,
        "created_at": user.created_at.isoformat() if getattr(user, "created_at", None) else None,
    }


def _format_memo(memo: Any) -> dict[str, Any]:
    return {
        "feedback_text": memo.feedback_text,
        "vocabulary_words": memo.vocabulary_words,
        "pronunciation_notes": memo.pronunciation_notes,
        "grammar_notes": memo.grammar_notes,
        "homework": memo.homework,
        "submitted_at": memo.submitted_at.isoformat(),
    }


def _extract_student_bookings(user: Any) -> list[dict[str, Any]]:
    bookings = []
    qs = (
        user.student_bookings.select_related("teacher__user", "material")
        .prefetch_related("memo")
        .order_by("-start_time_utc")[:500]
    )
    for b in qs:
        rec: dict[str, Any] = {
            "booking_id": str(b.id),
            "start_time_utc": b.start_time_utc.isoformat(),
            "end_time_utc": b.end_time_utc.isoformat(),
            "status": b.status,
            "tutor_name": b.teacher.user.get_full_name() or b.teacher.user.username,
            "curriculum_topic": b.material.title if b.material else None,
            "cancelled_at": b.cancelled_at.isoformat() if b.cancelled_at else None,
            "cancel_reason": b.cancel_reason if b.cancel_reason else None,
        }
        if getattr(b, "memo", None):
            rec["lesson_memo"] = _format_memo(b.memo)
        bookings.append(rec)
    return bookings


def _extract_student_credits(user: Any) -> list[dict[str, Any]]:
    credits_list = []
    if hasattr(user, "credit_bundles"):
        for bundle in user.credit_bundles.order_by("-created_at")[:100]:
            credits_list.append({
                "bundle_id": str(bundle.id),
                "pack_name": bundle.pack_name,
                "total_credits": bundle.total_credits,
                "remaining_credits": bundle.remaining_credits,
                "source": bundle.source,
                "expires_at": bundle.expires_at.isoformat() if bundle.expires_at else None,
                "created_at": bundle.created_at.isoformat() if getattr(bundle, "created_at", None) else None,
            })
    return credits_list


def _extract_teacher_data(user: Any) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    tp = getattr(user, "teacher_profile", None)
    if not tp:
        return None, []

    profile_dict = {
        "headline": tp.headline,
        "bio": tp.bio,
        "accent": tp.accent,
        "specialties": tp.specialties,
        "status": tp.status,
        "rating_avg": str(tp.rating_avg),
        "rating_count": tp.rating_count,
        "has_inverter_backup": tp.has_inverter_backup,
        "has_lte_failover": tp.has_lte_failover,
        "sla_strikes": tp.sla_strikes,
        "training_completed_at": tp.training_completed_at.isoformat() if tp.training_completed_at else None,
        "created_at": tp.created_at.isoformat() if tp.created_at else None,
    }

    lessons = []
    qs = (
        tp.bookings.select_related("student", "material")
        .prefetch_related("memo")
        .order_by("-start_time_utc")[:500]
    )
    for b in qs:
        rec: dict[str, Any] = {
            "booking_id": str(b.id),
            "start_time_utc": b.start_time_utc.isoformat(),
            "end_time_utc": b.end_time_utc.isoformat(),
            "status": b.status,
            "student_name": b.student.get_full_name() or b.student.username,
            "curriculum_topic": b.material.title if b.material else None,
        }
        if getattr(b, "memo", None):
            rec["lesson_memo"] = _format_memo(b.memo)
        lessons.append(rec)

    return profile_dict, lessons


def _extract_notifications(user: Any) -> dict[str, Any]:
    prefs: dict[str, dict[str, bool]] = {}
    if hasattr(user, "notification_preferences"):
        for pref in user.notification_preferences.all():
            prefs[pref.kind] = {"in_app": pref.in_app, "email": pref.email}

    history: list[dict[str, Any]] = []
    if hasattr(user, "notifications"):
        for n in user.notifications.order_by("-created_at")[:100]:
            history.append({
                "kind": n.kind,
                "title": n.title,
                "body": n.body,
                "created_at": n.created_at.isoformat(),
                "read_at": n.read_at.isoformat() if n.read_at else None,
            })

    return {"preferences": prefs, "in_app_history": history}


def _extract_support(user: Any) -> list[dict[str, Any]]:
    inquiries = []
    if hasattr(user, "support_inquiries"):
        for inq in user.support_inquiries.order_by("-created_at")[:50]:
            inquiries.append({
                "inquiry_id": str(inq.id),
                "subject": inq.subject,
                "message": inq.message,
                "status": inq.status,
                "created_at": inq.created_at.isoformat(),
            })
    return inquiries


def build_user_data_export(user: Any) -> dict[str, Any]:
    """
    Compile a complete, sanitized export of the user's personal data.
    Strictly redacts internal liability ledgers, gateway API secrets, and internal reviewer notes.
    """
    now_utc = datetime.now(timezone.utc).isoformat()
    export_id = f"SAR-{uuid.uuid4().hex[:12].upper()}"

    payload: dict[str, Any] = {
        "export_metadata": {
            "sar_reference": export_id,
            "generated_at_utc": now_utc,
            "jurisdiction_compliance": ["POPIA (Act 4 of 2013 - South Africa)", "GDPR (Regulation EU 2016/679)"],
            "legal_basis": "Data Subject Access Request (GDPR Art. 15 / POPIA Section 23)",
            "data_controller": "Sharon Online (Pty) Ltd.",
        },
        "account_profile": _extract_profile(user),
        "notifications": _extract_notifications(user),
        "support_inquiries": _extract_support(user),
    }

    sp = getattr(user, "student_profile", None)
    if sp:
        payload["student_profile"] = {
            "target_level": sp.target_level,
            "learning_goals": sp.learning_goals,
            "created_at": sp.created_at.isoformat() if sp.created_at else None,
        }

    if user.role == User.Role.STUDENT:
        payload["student_bookings"] = _extract_student_bookings(user)
        payload["credit_allowances"] = _extract_student_credits(user)

    teacher_profile, conducted_lessons = _extract_teacher_data(user)
    if teacher_profile is not None:
        payload["teacher_profile"] = teacher_profile
        payload["conducted_lessons"] = conducted_lessons

    return payload


def generate_user_data_zip(user: Any) -> bytes:
    """
    Generate a secure ZIP archive containing the JSON data export and legal notices.
    """
    data_dict = build_user_data_export(user)
    json_bytes = json.dumps(data_dict, indent=2, ensure_ascii=False).encode("utf-8")

    readme_content = f"""Sharon Online - Personal Data Subject Access Request (SAR) Export
Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%SZ')}
Data Subject: {user.username} ({user.email})
Reference: {data_dict['export_metadata']['sar_reference']}

--------------------------------------------------------------------------------
ABOUT THIS EXPORT
--------------------------------------------------------------------------------
This archive contains an export of your personal data held by Sharon Online (Pty) Ltd.
in accordance with Section 23 of the Protection of Personal Information Act (POPIA)
and Article 15 of the General Data Protection Regulation (GDPR).

Files included:
1. data_export.json - Your profile, lesson history, memos, notification settings, and support tickets in standard structured JSON format.
2. README.txt - This data summary and explanation of your rights.

--------------------------------------------------------------------------------
YOUR DATA RIGHTS
--------------------------------------------------------------------------------
You have the right to:
- Request correction or updating of your personal information.
- Request deletion of your account and personal records (subject to statutory financial retention requirements).
- Object to the processing of your personal data where applicable.

For inquiries or to exercise your rights, contact our Data Protection Officer at:
privacy@sharonesl.com
Sharon Online (Pty) Ltd.
Cape Town, South Africa
"""

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("data_export.json", json_bytes)
        zf.writestr("README.txt", readme_content.encode("utf-8"))

    return buf.getvalue()
