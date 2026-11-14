"""``POST /api/plugins/ai-import/preview/`` -- try a prompt without saving.

The household's complaint that started this was "I cannot see what the prompt
does". A settings field alone answers that with hope. This endpoint runs the
same pipeline against a URL and returns only the steps, so the settings page
can show the result beside the field.

Nothing is created: no recipe, no food, no unit. The test counts them, because
the first version of the import endpoint passed a test that only counted
recipes while quietly creating every ingredient's food.
"""

from __future__ import annotations

import json
import traceback

import litellm
from cookbook.helper.ai_helper import AiCallbackHandler, can_perform_ai_request
from cookbook.models import AiLog, AiProvider, Food, Recipe, Unit
from cookbook.views.api import AiEndpointThrottle
from django.conf import settings
from django.db.models import Q
from django.utils.translation import gettext_lazy as _
from django_scopes import scopes_disabled
from litellm.exceptions import BadRequestError, Timeout as LitellmTimeout
from rest_framework import serializers, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from . import prompt, shaping, source
from .models import settings_for
from .views import MAX_TOKENS, _vocabulary, completion_model


class PreviewRequestSerializer(serializers.Serializer):
    url = serializers.CharField(required=False, allow_blank=True, max_length=2048)
    text = serializers.CharField(required=False, allow_blank=True)
    ai_provider_id = serializers.IntegerField()
    custom_prompt = serializers.CharField(required=False, allow_blank=True, allow_null=True)

    def validate(self, attrs):
        if not (attrs.get('url') or '').strip() and not (attrs.get('text') or '').strip():
            raise serializers.ValidationError('URL oder Text angeben')
        return attrs


class PreviewView(APIView):
    """Returns the shaped steps for a draft prompt; writes nothing to the library."""

    throttle_classes = [AiEndpointThrottle]
    permission_classes = [IsAuthenticated]

    def post(self, request, *args, **kwargs):
        serializer = PreviewRequestSerializer(data=request.data)
        if not serializer.is_valid():
            return Response({'error': True, 'msg': serializer.errors},
                            status=status.HTTP_400_BAD_REQUEST)

        if not can_perform_ai_request(request.space):
            return Response({'error': True, 'msg': _('AI ist für diesen Space ausgeschaltet.')},
                            status=status.HTTP_400_BAD_REQUEST)

        with scopes_disabled():
            provider = (AiProvider.objects
                        .filter(pk=serializer.validated_data['ai_provider_id'])
                        .filter(Q(space=request.space) | Q(space__isnull=True))
                        .first())
        if provider is None:
            return Response({'error': True, 'msg': _('Unbekannter AI-Provider.')},
                            status=status.HTTP_400_BAD_REQUEST)
        if provider.url and provider.url not in settings.AI_ALLOWED_URLS:
            return Response({'error': True, 'msg': f'AI provider URL not allowed: {provider.url}'},
                            status=status.HTTP_400_BAD_REQUEST)

        url = (serializer.validated_data.get('url') or '').strip()
        try:
            if url:
                text, _canonical = source.source_from_url(url)
                source_kind = 'url'
            else:
                text, _canonical = source.source_from_text(serializer.validated_data['text']), ''
                source_kind = 'text'
        except source.FetchError as exc:
            return Response({'error': True, 'msg': str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        space_settings = settings_for(request.space)
        # A draft prompt from the settings page wins; otherwise the saved one.
        custom_prompt = serializer.validated_data.get('custom_prompt')
        if custom_prompt is None:
            custom_prompt = space_settings.custom_prompt

        vocab = _vocabulary(request.space)
        messages = prompt.build_messages(
            text, source_kind=source_kind,
            known_foods=vocab['foods'], known_units=vocab['units'],
            known_tags=vocab['tags'], custom_prompt=custom_prompt,
        )

        litellm.callbacks = [AiCallbackHandler(request.space, request.user, provider, AiLog.F_FILE_IMPORT)]
        ai_request = {
            'api_key': provider.api_key,
            'model': completion_model(provider.model_name),
            'response_format': {'type': 'json_object'},
            'messages': messages,
            'max_tokens': MAX_TOKENS,
        }
        if provider.url:
            ai_request['api_base'] = provider.url

        try:
            completion = litellm.completion(**ai_request)
        except LitellmTimeout:
            return Response({'error': True, 'msg': _('Die AI hat zu lange gebraucht.')},
                            status=status.HTTP_408_REQUEST_TIMEOUT)
        except BadRequestError as exc:
            return Response({'error': True, 'msg': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception:
            traceback.print_exc()
            return Response({'error': True, 'msg': _('Die AI-Antwort ist fehlgeschlagen.')},
                            status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        try:
            answer = shaping.parse_model_answer(completion.choices[0].message.content or '')
        except shaping.ShapeError as exc:
            return Response({'error': True, 'msg': f'Die AI-Antwort war unbrauchbar: {exc}'},
                            status=status.HTTP_422_UNPROCESSABLE_ENTITY)

        # Preview uses the saved switches so what is shown is what an import
        # would produce; the prompt is the only thing that is a draft.
        try:
            recipe = shaping.to_recipe_payload(
                answer, units=vocab['unit_index'], foods=vocab['food_index'], keywords=[],
                options={
                    'placeholders_enabled': space_settings.placeholders_enabled,
                    'enforce_step_titles': space_settings.enforce_step_titles,
                },
            )
        except shaping.ShapeError as exc:
            return Response({'error': True, 'msg': f'Die AI-Antwort war unbrauchbar: {exc}'},
                            status=status.HTTP_422_UNPROCESSABLE_ENTITY)

        return Response({
            'recipe': {'name': recipe['name'], 'steps': recipe['steps']},
            'counts': {
                # So the page can say "7 foods are not in your library yet"
                # without the operator opening a second tab.
                'unknown_foods': len([
                    name for name in _food_names(recipe)
                    if name not in vocab['food_index']
                ]),
            },
        }, status=status.HTTP_200_OK)


def _food_names(recipe: dict) -> list[str]:
    from .vocabulary import food_key
    names = []
    for step in recipe.get('steps') or []:
        for ingredient in step.get('ingredients') or []:
            if ingredient.get('is_header'):
                continue
            name = ((ingredient.get('food') or {}).get('name') or '').strip()
            if name:
                names.append(food_key(name))
    return names
