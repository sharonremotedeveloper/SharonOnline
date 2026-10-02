from rest_framework.views import APIView
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework.response import Response
from rest_framework import status
from django.shortcuts import get_object_or_404

from apps.users.permissions import IsTeacherOrAdmin
from apps.crm.models import StudentTutorDossier
from apps.crm.serializers import TeacherStudentDossierSerializer, DossierUpdateSerializer
from apps.users.models import User
from apps.bookings.models import Booking
from apps.teachers.models import TeacherProfile

@extend_schema(request=OpenApiTypes.OBJECT, responses=OpenApiTypes.OBJECT)  # TODO(8.8+): replace with typed serializers
class TeacherStudentDossierListView(APIView):
    permission_classes = [IsTeacherOrAdmin]

    def get(self, request):
        if hasattr(request.user, 'teacher_profile'):
            teacher = request.user.teacher_profile
            dossiers = StudentTutorDossier.objects.filter(teacher=teacher).select_related('student', 'teacher')
        else:
            # Fallback for platform admin reviewing dossiers
            dossiers = StudentTutorDossier.objects.all().select_related('student', 'teacher')

        serializer = TeacherStudentDossierSerializer(dossiers, many=True)
        return Response(serializer.data)


@extend_schema(request=OpenApiTypes.OBJECT, responses=OpenApiTypes.OBJECT)  # TODO(8.8+): replace with typed serializers
class TeacherStudentDossierUpdateView(APIView):
    permission_classes = [IsTeacherOrAdmin]

    def patch(self, request, student_id):
        serializer = DossierUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        student = get_object_or_404(User, pk=student_id)

        if hasattr(request.user, 'teacher_profile'):
            teacher = request.user.teacher_profile
            # A tutor may only keep notes on students they actually teach (or already have a dossier for).
            has_relationship = (
                Booking.objects.filter(teacher=teacher, student=student).exists()
                or StudentTutorDossier.objects.filter(teacher=teacher, student=student).exists()
            )
            if not has_relationship:
                return Response({'error': 'You have no lesson history with this student.'}, status=status.HTTP_403_FORBIDDEN)
        else:
            # Platform admin: must explicitly name the tutor; never guess.
            teacher_id = request.data.get('teacher_id')
            teacher = TeacherProfile.objects.filter(pk=teacher_id).first() if teacher_id else None
            if not teacher:
                return Response({'error': 'teacher_id is required for admin edits'}, status=status.HTTP_400_BAD_REQUEST)

        dossier, _ = StudentTutorDossier.objects.get_or_create(
            teacher=teacher,
            student=student
        )

        if 'private_pedagogical_notes' in serializer.validated_data:
            dossier.private_pedagogical_notes = serializer.validated_data['private_pedagogical_notes']
        if 'common_grammar_mistakes' in serializer.validated_data:
            dossier.common_grammar_mistakes = serializer.validated_data['common_grammar_mistakes']

        dossier.save()

        return Response({
            'success': True,
            'message': "Student pedagogical dossier updated successfully."
        })
