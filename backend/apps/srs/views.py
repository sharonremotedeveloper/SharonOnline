from rest_framework.views import APIView
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework.response import Response
from rest_framework import status
from django.utils import timezone
from datetime import timedelta
from django.shortcuts import get_object_or_404

from apps.users.permissions import IsStudent
from apps.srs.models import StudentFlashcard
from apps.bookings.models import Booking
from apps.srs.serializers import (
    StudentFlashcardSerializer,
    FlashcardMasteryUpdateSerializer,
    StudentLessonItemSerializer,
    StudentProfileSerializer,
)

@extend_schema(request=OpenApiTypes.OBJECT, responses=OpenApiTypes.OBJECT)  # TODO(8.8+): replace with typed serializers
class StudentLessonsListView(APIView):
    permission_classes = [IsStudent]

    def get(self, request):
        lessons = Booking.objects.filter(student=request.user).select_related(
            'teacher', 'teacher__user', 'material', 'student'
        ).prefetch_related('memo').order_by('-start_time_utc')
        serializer = StudentLessonItemSerializer(lessons, many=True)
        return Response(serializer.data)


@extend_schema(request=OpenApiTypes.OBJECT, responses=OpenApiTypes.OBJECT)  # TODO(8.8+): replace with typed serializers
class StudentFlashcardsListView(APIView):
    permission_classes = [IsStudent]

    def get(self, request):
        cards = StudentFlashcard.objects.filter(student=request.user).order_by('next_review_due')
        serializer = StudentFlashcardSerializer(cards, many=True)
        return Response(serializer.data)


@extend_schema(request=OpenApiTypes.OBJECT, responses=OpenApiTypes.OBJECT)  # TODO(8.8+): replace with typed serializers
class UpdateFlashcardMasteryView(APIView):
    permission_classes = [IsStudent]

    def post(self, request, pk):
        card = get_object_or_404(StudentFlashcard, pk=pk, student=request.user)
        serializer = FlashcardMasteryUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        grade = serializer.validated_data['grade']

        today = timezone.now().date()
        if grade == 'easy':
            card.mastery = StudentFlashcard.Mastery.MASTERED
            card.next_review_due = today + timedelta(days=7)
        elif grade == 'good':
            card.mastery = StudentFlashcard.Mastery.LEARNING
            card.next_review_due = today + timedelta(days=3)
        else: # again
            card.mastery = StudentFlashcard.Mastery.NEW
            card.next_review_due = today + timedelta(days=1)

        card.review_count += 1
        card.save()

        return Response({
            'success': True,
            'nextReview': card.next_review_due.strftime('%Y-%m-%d'),
            'mastery': card.mastery
        })


@extend_schema(request=OpenApiTypes.OBJECT, responses=OpenApiTypes.OBJECT)  # TODO(8.8+): replace with typed serializers
class StudentProfileView(APIView):
    permission_classes = [IsStudent]

    def get(self, request):
        user = request.user
        target_level = getattr(user, 'target_level', "C1 - Advanced Fluency")
        learning_goals = getattr(user, 'learning_goals', "Conduct seamless cross-border product design reviews and expand active vocabulary.")

        return Response({
            'id': str(user.id),
            'full_name': user.get_full_name() or user.username,
            'email': user.email,
            'country': user.country or "Japan",
            'timezone': user.timezone or "Asia/Tokyo",
            'target_level': target_level,
            'learning_goals': learning_goals
        })

    def patch(self, request):
        user = request.user
        data = request.data

        if 'full_name' in data:
            parts = data['full_name'].split(' ', 1)
            user.first_name = parts[0]
            if len(parts) > 1:
                user.last_name = parts[1]

        if 'country' in data:
            user.country = data['country'][:2].upper()
        if 'timezone' in data:
            user.timezone = data['timezone']

        target_level = data.get('target_level', getattr(user, 'target_level', "C1 - Advanced Fluency"))
        learning_goals = data.get('learning_goals', getattr(user, 'learning_goals', "Conduct seamless cross-border product design reviews."))

        user.save()

        return Response({
            'success': True,
            'profile': {
                'id': str(user.id),
                'full_name': user.get_full_name() or user.username,
                'email': user.email,
                'country': user.country,
                'timezone': user.timezone,
                'target_level': target_level,
                'learning_goals': learning_goals
            }
        })
