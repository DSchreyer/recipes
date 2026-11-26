"""``/api/plugins/ai-import/settings/`` -- read and write the space's switches.

One row per space, created on the first save. The GET never writes: an empty
answer means "defaults", and the settings page shows exactly what the import
will do, not an empty form pretending to be configuration.
"""

from __future__ import annotations

from django_scopes import scopes_disabled
from rest_framework import serializers, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import AiImportSettings, settings_for
from .prompt import WISH_SYSTEM


class SettingsSerializer(serializers.ModelSerializer):
    class Meta:
        model = AiImportSettings
        fields = ('placeholders_enabled', 'images_enabled', 'enforce_step_titles',
                  'wish_prompt', 'custom_prompt')

    def validate_custom_prompt(self, value: str) -> str:
        return (value or '').strip()

    def validate_wish_prompt(self, value: str) -> str:
        """Blank means the built-in brief, so blank is stored as blank."""
        return (value or '').strip()


class SettingsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        row = settings_for(request.space)
        return Response({
            'placeholders_enabled': row.placeholders_enabled,
            'images_enabled': row.images_enabled,
            'enforce_step_titles': row.enforce_step_titles,
            'wish_prompt': row.wish_prompt,
            # The text the page starts an editor from. Sent along so the
            # household edits the prompt that is actually in use instead of a
            # copy that drifts from it.
            'wish_prompt_default': WISH_SYSTEM,
            'custom_prompt': row.custom_prompt,
            'stored': row.pk is not None,
        })

    def put(self, request, *args, **kwargs):
        serializer = SettingsSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        with scopes_disabled():
            row, _created = AiImportSettings.objects.get_or_create(space=request.space)
            for field, value in serializer.validated_data.items():
                setattr(row, field, value)
            row.save()
        return Response({
            **{f: getattr(row, f) for f in SettingsSerializer.Meta.fields},
            'wish_prompt_default': WISH_SYSTEM,
            'stored': True,
        }, status=status.HTTP_200_OK)


__all__ = ['SettingsView', 'SettingsSerializer']
