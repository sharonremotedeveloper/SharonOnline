from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta, time
import uuid

from apps.users.models import User
from apps.teachers.models import TeacherProfile, TeacherAvailability
from apps.teachers.vetting import create_teacher_profile
from apps.bookings.models import Booking, LessonMemo, AttendanceAudit
from apps.materials.models import Material
from apps.payments.models import CreditBundle, PaymentTransaction
from apps.admin_api.models import DisputeCase, PayoutBatch
from apps.crm.models import StudentTutorDossier
from apps.srs.models import StudentFlashcard

class Command(BaseCommand):
    help = "Seeds comprehensive mock data for Phase 4.1: Admin Command Center, Teacher CRM, and Student SRS."

    def handle(self, *args, **kwargs):
        self.stdout.write("Seeding database with Phase 4.1 Admin, CRM, and SRS data...")

        now = timezone.now()

        # Retrieve core users
        admin_user = User.objects.filter(role=User.Role.ADMIN).first()
        student_aiko = User.objects.filter(username="student_aiko").first()
        tutor_naledi = TeacherProfile.objects.filter(user__username="naledi_tutor").first()

        # Ensure Kenji Sato exists as a student
        student_kenji, _ = User.objects.get_or_create(
            username="student_kenji",
            defaults={
                "email": "kenji.sato@example.jp",
                "first_name": "Kenji",
                "last_name": "Sato",
                "role": User.Role.STUDENT,
                "country": "JP",
                "timezone": "Asia/Tokyo"
            }
        )
        if _:
            student_kenji.set_password("password123")
            student_kenji.save()

        # Ensure Marco Rossi exists
        student_marco, _ = User.objects.get_or_create(
            username="student_marco",
            defaults={
                "email": "marco.rossi@example.it",
                "first_name": "Marco",
                "last_name": "Rossi",
                "role": User.Role.STUDENT,
                "country": "IT",
                "timezone": "Europe/Rome"
            }
        )
        if _:
            student_marco.set_password("password123")
            student_marco.save()

        # 1. Unverified Teacher Applicants for Vetting Studio
        unverified_tutors_data = [
            {
                "username": "thabo_applicant",
                "email": "thabo.n@example.co.za",
                "first_name": "Thabo",
                "last_name": "Ndlovu",
                "headline": "CELTA Certified · 4 Yrs Tokyo ESL Experience",
                "accent": TeacherProfile.Accent.SOUTH_AFRICAN,
                "bio": "CELTA-certified English teacher with 4 years tutoring Asian professionals in Tokyo and Taipei. Strong emphasis on business negotiation flow.",
                "price": 9.0,
                "specialties": ["Business English", "Pronunciation", "STAR Interviewing"],
                "video_url": "https://assets.mixkit.co/videos/preview/mixkit-young-man-giving-a-presentation-online-41292-large.mp4",
                "country": "ZA",
                "timezone": "Africa/Johannesburg"
            },
            {
                "username": "kirsty_applicant",
                "email": "kirsty.vz@example.co.za",
                "first_name": "Kirsty",
                "last_name": "van Zyl",
                "headline": "IELTS Specialist · Academic Phrasing Coach",
                "accent": TeacherProfile.Accent.BRITISH,
                "bio": "Specializing in IELTS preparation and academic writing. Former high school English literature instructor.",
                "price": 8.5,
                "specialties": ["IELTS Prep", "Grammar Drills", "FreeTalk"],
                "video_url": "https://assets.mixkit.co/videos/preview/mixkit-woman-in-online-meeting-41290-large.mp4",
                "country": "ZA",
                "timezone": "Africa/Johannesburg"
            },
            {
                "username": "zanele_applicant",
                "email": "zanele.k@example.co.za",
                "first_name": "Zanele",
                "last_name": "Khumalo",
                "headline": "Conversational Fluency · Anxiety Reduction Specialist",
                "accent": TeacherProfile.Accent.SOUTH_AFRICAN,
                "bio": "Friendly conversationalist focusing on beginners and children. Expert at reducing anxiety in introductory speaking classes.",
                "price": 8.0,
                "specialties": ["Beginner A1-A2", "Conversation", "Travel English"],
                "video_url": "https://assets.mixkit.co/videos/preview/mixkit-young-woman-in-online-meeting-41290-large.mp4",
                "country": "ZA",
                "timezone": "Africa/Johannesburg"
            }
        ]

        for item in unverified_tutors_data:
            user, created = User.objects.get_or_create(
                username=item["username"],
                defaults={
                    "email": item["email"],
                    "first_name": item["first_name"],
                    "last_name": item["last_name"],
                    "role": User.Role.TEACHER,
                    "country": item["country"],
                    "timezone": item["timezone"]
                }
            )
            if created:
                user.set_password("password123")
                user.save()

            # Applications waiting in the vetting queue, created through the status service; idempotent on re-runs.
            if not TeacherProfile.objects.filter(user=user).exists():
                create_teacher_profile(
                    user,
                    status=TeacherProfile.Status.SUBMITTED,
                    actor="system:seed_phase41_data",
                    reason="seed",
                    headline=item["headline"],
                    accent=item["accent"],
                    bio=item["bio"],
                    price_per_25min_usd=item["price"],
                    specialties=item["specialties"],
                    intro_video_url=item["video_url"],
                )
        self.stdout.write("Created 3 pending tutor applications in vetting queue.")

        # 2. Live & Recent Bookings with Attendance Audits
        material_b2 = Material.objects.filter(cefr_level=Material.CEFRLevel.B2).first()
        if tutor_naledi and student_aiko:
            booking_live, _ = Booking.objects.get_or_create(
                teacher=tutor_naledi,
                student=student_aiko,
                start_time_utc=now - timedelta(minutes=12),
                defaults={
                    "end_time_utc": now + timedelta(minutes=13),
                    "material": material_b2,
                    "status": Booking.Status.IN_PROGRESS,
                    "zoom_meeting_id": "987 654 3210",
                    "zoom_join_url": "https://zoom.us/j/9876543210?pwd=ESL_CLASS_ROOM"
                }
            )
            AttendanceAudit.objects.get_or_create(
                booking=booking_live,
                participant_email=student_aiko.email,
                defaults={"join_time_utc": now - timedelta(minutes=12), "total_minutes": 12}
            )
            AttendanceAudit.objects.get_or_create(
                booking=booking_live,
                participant_email=tutor_naledi.user.email,
                defaults={"join_time_utc": now - timedelta(minutes=13), "total_minutes": 13}
            )

        # 3. Dispute Cases with statements and telemetry
        if tutor_naledi and student_marco:
            booking_disp1, _ = Booking.objects.get_or_create(
                teacher=tutor_naledi,
                student=student_marco,
                start_time_utc=now - timedelta(days=1, hours=2),
                defaults={
                    "end_time_utc": now - timedelta(days=1, hours=1, minutes=35),
                    "status": Booking.Status.DISPUTED
                }
            )
            AttendanceAudit.objects.get_or_create(
                booking=booking_disp1,
                participant_email=student_marco.email,
                defaults={"join_time_utc": now - timedelta(days=1, hours=2), "total_minutes": 10}
            )
            AttendanceAudit.objects.get_or_create(
                booking=booking_disp1,
                participant_email=tutor_naledi.user.email,
                defaults={"join_time_utc": now - timedelta(days=1, hours=2), "total_minutes": 25}
            )
            DisputeCase.objects.get_or_create(
                booking=booking_disp1,
                defaults={
                    "student": student_marco,
                    "teacher": tutor_naledi,
                    "student_statement": "Tutor did not join the Zoom call for the first 15 minutes. When she joined, audio was stuttering heavily.",
                    "teacher_statement": "I was present in the meeting on time. The student had an incorrect meeting password cached in their browser.",
                    "status": DisputeCase.Status.OPEN
                }
            )

        if tutor_naledi and student_kenji:
            booking_disp2, _ = Booking.objects.get_or_create(
                teacher=tutor_naledi,
                student=student_kenji,
                start_time_utc=now - timedelta(days=2, hours=4),
                defaults={
                    "end_time_utc": now - timedelta(days=2, hours=3, minutes=35),
                    "status": Booking.Status.INTERRUPTED_POWER
                }
            )
            DisputeCase.objects.get_or_create(
                booking=booking_disp2,
                defaults={
                    "student": student_kenji,
                    "teacher": tutor_naledi,
                    "student_statement": "Session disconnected abruptly at minute 8 due to tutor load shedding.",
                    "teacher_statement": "Our municipal substation tripped under Stage 4 load shedding. Battery inverter engaged after 4 minutes.",
                    "status": DisputeCase.Status.OPEN
                }
            )
        self.stdout.write("Created 2 open dispute cases in arbitration tribunal.")

        # 4. Teacher Student CRM Dossiers
        if tutor_naledi:
            StudentTutorDossier.objects.get_or_create(
                teacher=tutor_naledi,
                student=student_kenji,
                defaults={
                    "private_pedagogical_notes": "Very diligent with vocabulary flashcards. Tends to over-rely on formal passive voice when discussing technical architecture. Encourage colloquial phrasal verbs and rapid-fire scenario debates.",
                    "common_grammar_mistakes": [
                        "Article omission ('the / a')",
                        "Second conditional inversion ('If I would have...')",
                        "Preposition collocations ('interested on' instead of 'interested in')"
                    ]
                }
            )

            StudentTutorDossier.objects.get_or_create(
                teacher=tutor_naledi,
                student=student_marco,
                defaults={
                    "private_pedagogical_notes": "High enthusiasm and energetic delivery. Needs ongoing focus on terminal consonant articulation ('think' vs 'thing'). Enjoys Daily News articles on automotive and green energy.",
                    "common_grammar_mistakes": [
                        "False friends ('actually' vs 'currently')",
                        "Word order in indirect questions ('where is it' -> 'where it is')"
                    ]
                }
            )
            self.stdout.write("Created 2 teacher-student pedagogical CRM dossiers.")

        # 5. Student SRS Flashcards
        flashcard_words = [
            {
                "word": "concession",
                "phonetic": "/kənˈseʃ.ən/",
                "part_of_speech": "noun",
                "definition": "A thing that is granted or yielded, especially in response to demands to reach an agreement.",
                "example_sentence": "The executive committee made significant concessions regarding the quarterly rollout timeline.",
                "lesson_source": "High-Stakes Contract Negotiations (Naledi M.)",
                "mastery": StudentFlashcard.Mastery.LEARNING,
                "review_count": 3,
                "days_due": 2
            },
            {
                "word": "deadlock",
                "phonetic": "/ˈded.lɒk/",
                "part_of_speech": "noun",
                "definition": "A situation involving opposing parties in which no progress can be made.",
                "example_sentence": "After three hours of intense cross-table debate, the partnership talks reached a deadlock.",
                "lesson_source": "High-Stakes Contract Negotiations (Naledi M.)",
                "mastery": StudentFlashcard.Mastery.NEW,
                "review_count": 0,
                "days_due": 0
            },
            {
                "word": "serendipitous",
                "phonetic": "/ˌser.ənˈdɪp.ɪ.təs/",
                "part_of_speech": "adjective",
                "definition": "Occurring or discovered by chance in a happy or beneficial way.",
                "example_sentence": "Their co-founding partnership was entirely serendipitous, beginning at a tech conference lounge.",
                "lesson_source": "Curriculum: Everyday Idioms",
                "mastery": StudentFlashcard.Mastery.LEARNING,
                "review_count": 4,
                "days_due": 3
            },
            {
                "word": "nuance",
                "phonetic": "/ˈnjuː.ɑːns/",
                "part_of_speech": "noun",
                "definition": "A subtle difference or distinction in expression, meaning, response, or tone.",
                "example_sentence": "Seasoned bilingual negotiators pay close attention to the cultural nuances in voice inflection.",
                "lesson_source": "Executive Presence & Nuance (Naledi M.)",
                "mastery": StudentFlashcard.Mastery.MASTERED,
                "review_count": 8,
                "days_due": 7
            },
            {
                "word": "mitigate",
                "phonetic": "/ˈmɪt.ɪ.ɡeɪt/",
                "part_of_speech": "verb",
                "definition": "Make something bad or harmful less severe, serious, or painful.",
                "example_sentence": "Installing dual-battery inverter systems helped the engineering team mitigate municipal grid drops.",
                "lesson_source": "Curriculum: AI & Infrastructure",
                "mastery": StudentFlashcard.Mastery.NEW,
                "review_count": 1,
                "days_due": 1
            },
            {
                "word": "leverage",
                "phonetic": "/ˈliː.vər.ɪdʒ/",
                "part_of_speech": "verb / noun",
                "definition": "Use something to maximum advantage; the exertive power to influence outcomes.",
                "example_sentence": "The startup leveraged its proprietary algorithmic patents to negotiate favorable venture terms.",
                "lesson_source": "High-Stakes Contract Negotiations (Naledi M.)",
                "mastery": StudentFlashcard.Mastery.MASTERED,
                "review_count": 6,
                "days_due": 6
            }
        ]

        target_student = student_kenji or student_aiko
        if target_student:
            for item in flashcard_words:
                StudentFlashcard.objects.update_or_create(
                    student=target_student,
                    word=item["word"],
                    defaults={
                        "phonetic": item["phonetic"],
                        "part_of_speech": item["part_of_speech"],
                        "definition": item["definition"],
                        "example_sentence": item["example_sentence"],
                        "lesson_source": item["lesson_source"],
                        "mastery": item["mastery"],
                        "review_count": item["review_count"],
                        "next_review_due": (now + timedelta(days=item["days_due"])).date()
                    }
                )
            self.stdout.write(f"Created 6 SRS flashcards for student: {target_student.username}")

        self.stdout.write(self.style.SUCCESS("Phase 4.1 mock database seeding completed successfully!"))
