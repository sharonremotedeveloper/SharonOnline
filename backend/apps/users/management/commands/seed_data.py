from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import time
from apps.users.models import User
from apps.teachers.models import TeacherProfile, TeacherAvailability
from apps.teachers.vetting import create_teacher_profile
from apps.materials.models import Material

class Command(BaseCommand):
    help = "Seeds initial realistic demo users, tutors, availabilities, and curriculum materials."

    def handle(self, *args, **kwargs):
        self.stdout.write("Seeding database with demo data...")

        # 1. Admin User
        admin_user, created = User.objects.get_or_create(
            username="admin",
            defaults={
                "email": "sharon@sharonesl.com",
                "first_name": "Sharon",
                "last_name": "Founder",
                "role": User.Role.ADMIN,
                "is_staff": True,
                "is_superuser": True,
                "country": "ZA",
                "timezone": "Africa/Johannesburg"
            }
        )
        if created:
            admin_user.set_password("password123")
            admin_user.save()
            self.stdout.write("Created admin user: admin / password123")

        # 2. Test Student
        student_user, created = User.objects.get_or_create(
            username="student_aiko",
            defaults={
                "email": "aiko@example.jp",
                "first_name": "Aiko",
                "last_name": "Tanaka",
                "role": User.Role.STUDENT,
                "country": "JP",
                "timezone": "Asia/Tokyo"
            }
        )
        if created:
            student_user.set_password("password123")
            student_user.save()
            self.stdout.write("Created student: student_aiko / password123")

        # 3. Tutors
        tutor_data = [
            {
                "username": "naledi_tutor",
                "email": "naledi@sharonesl.com",
                "first_name": "Naledi",
                "last_name": "Molefe",
                "headline": "Certified TEFL Tutor · 6+ Yrs Experience · Business & Daily News",
                "accent": TeacherProfile.Accent.SOUTH_AFRICAN,
                "bio": "Hi! I'm Naledi from Johannesburg, South Africa. I specialize in helping Japanese and European professionals build fluid speaking confidence for global business meetings, presentations, and daily conversation.",
                "rating_avg": 4.98,
                "rating_count": 142,
                "price": 9.00,
                "specialties": ["Business English", "Daily News", "FreeTalk", "Pronunciation"],
                "intro_video": "https://commondatastorage.googleapis.com/gtv-videos-bucket/sample/BigBuckBunny.mp4",
                "avatar": "https://images.unsplash.com/photo-1573496359142-b8d87734a5a2?auto=format&fit=crop&q=80&w=300",
                "country": "ZA",
                "timezone": "Africa/Johannesburg"
            },
            {
                "username": "david_tutor",
                "email": "david@sharonesl.com",
                "first_name": "David",
                "last_name": "Smith",
                "headline": "Cambridge CELTA Certified · IELTS & TOEIC Test Prep Specialist",
                "accent": TeacherProfile.Accent.BRITISH,
                "bio": "Hello there! I'm David from Oxford, UK. With over 8 years of ESL coaching in Tokyo and Seoul, I focus on high-score exam strategies and native British phrasing.",
                "rating_avg": 4.95,
                "rating_count": 98,
                "price": 10.00,
                "specialties": ["IELTS/TOEIC", "Grammar Mastery", "Business English"],
                "intro_video": "https://commondatastorage.googleapis.com/gtv-videos-bucket/sample/ElephantsDream.mp4",
                "avatar": "https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?auto=format&fit=crop&q=80&w=300",
                "country": "GB",
                "timezone": "Europe/London"
            },
            {
                "username": "charlotte_tutor",
                "email": "charlotte@sharonesl.com",
                "first_name": "Charlotte",
                "last_name": "Van Der Merwe",
                "headline": "Cape Town University Graduate · Warm, Encouraging Conversation Coach",
                "accent": TeacherProfile.Accent.SOUTH_AFRICAN,
                "bio": "Welcome! I'm Charlotte from Cape Town. My classes are relaxed, friendly, and structured to get you talking immediately. Mistakes are just learning opportunities!",
                "rating_avg": 4.92,
                "rating_count": 87,
                "price": 8.50,
                "specialties": ["FreeTalk", "Daily News", "Beginner Friendly"],
                "intro_video": "https://commondatastorage.googleapis.com/gtv-videos-bucket/sample/ForBiggerBlazes.mp4",
                "avatar": "https://images.unsplash.com/photo-1580489944761-15a19d654956?auto=format&fit=crop&q=80&w=300",
                "country": "ZA",
                "timezone": "Africa/Johannesburg"
            }
        ]

        for item in tutor_data:
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

            # Approved, trained tutors, created through the status service (baseline audit row); idempotent on re-runs.
            profile = TeacherProfile.objects.filter(user=user).first() or create_teacher_profile(
                user,
                status=TeacherProfile.Status.APPROVED,
                actor="system:seed_data",
                reason="seed",
                training_completed_at=timezone.now(),
                headline=item["headline"],
                accent=item["accent"],
                bio=item["bio"],
                rating_avg=item["rating_avg"],
                rating_count=item["rating_count"],
                price_per_25min_usd=item["price"],
                specialties=item["specialties"],
                intro_video_url=item["intro_video"],
                avatar_url=item["avatar"],
            )

            # Weekly availability: Mon to Fri 08:00 to 18:00
            for day in range(0, 5):
                TeacherAvailability.objects.get_or_create(
                    teacher=profile,
                    day_of_week=day,
                    start_time=time(8, 0),
                    end_time=time(18, 0),
                    defaults={"is_active": True}
                )

            self.stdout.write(f"Created tutor: {item['first_name']} {item['last_name']} with availability Mon-Fri 08:00-18:00")

        # 4. Curriculum Materials
        materials_data = [
            {
                "title": "Global Remote Work Trends in 2026",
                "slug": "global-remote-work-trends-2026",
                "category": Material.Category.DAILY_NEWS,
                "cefr_level": Material.CEFRLevel.B2,
                "description": "Examine how international corporations are adapting hybrid work models across Tokyo, London, and Johannesburg.",
                "content_html": "<h3>Vocabulary Focus</h3><ul><li><strong>Asynchronous:</strong> Communication not occurring in real time.</li><li><strong>Autonomy:</strong> The freedom to self-govern.</li></ul><h3>Discussion Questions</h3><ol><li>How does your company handle remote meetings?</li><li>What are the advantages of asynchronous collaboration?</li></ol>"
            },
            {
                "title": "Introducing Yourself with Executive Impact",
                "slug": "introducing-yourself-executive-impact",
                "category": Material.Category.BUSINESS,
                "cefr_level": Material.CEFRLevel.B1,
                "description": "Learn professional phrasing for client kickoff calls, internal standups, and stakeholder presentations.",
                "content_html": "<h3>Key Phrases</h3><ul><li>'I lead the digital engineering initiatives for...'</li><li>'My primary focus over the next quarter is...'</li></ul>"
            },
            {
                "title": "Weekend Activities & Hobbies",
                "slug": "weekend-activities-and-hobbies",
                "category": Material.Category.FREETALK,
                "cefr_level": Material.CEFRLevel.A2,
                "description": "Simple, comfortable conversation prompts for sharing what you enjoy doing in your spare time.",
                "content_html": "<h3>Conversation Starters</h3><ol><li>What do you usually do on Saturday mornings?</li><li>Have you tried any new hobbies recently?</li></ol>"
            },
            {
                "title": "Mastering the Behavioral Interview (STAR Technique)",
                "slug": "mastering-behavioral-interview-star",
                "category": Material.Category.TEST_PREP,
                "cefr_level": Material.CEFRLevel.C1,
                "description": "Structure your answers using Situation, Task, Action, and Result for international corporate interviews.",
                "content_html": "<h3>STAR Framework Breakdown</h3><p>Learn how to concisely describe complex technical and managerial challenges.</p>"
            }
        ]

        for m in materials_data:
            mat, created = Material.objects.get_or_create(
                slug=m["slug"],
                defaults={
                    "title": m["title"],
                    "category": m["category"],
                    "cefr_level": m["cefr_level"],
                    "description": m["description"],
                    "content_html": m["content_html"],
                    "is_approved": True
                }
            )
            if created:
                self.stdout.write(f"Created material: {mat.title}")

        self.stdout.write(self.style.SUCCESS("Database seeding completed successfully!"))
