"""``POST /plugins/ai-import/from-source/``

One endpoint, two inputs: a URL to crawl, or free text describing a dish. The
answer is the same shape Tandoor's import dialog already consumes, so the
household reviews it in the editor and saves it there.

What this deliberately reuses instead of rebuilding:

* ``AiProvider`` — the space's provider row, which in Atlas points at LiteLLM.
  No second place to configure a model, no key in this plugin.
* ``can_perform_ai_request`` — ``Space.ai_enabled`` and credits, which is the
  per-space off switch the household asked for.
* ``AI_ALLOWED_URLS`` — Tandoor's own guard on a provider URL.
* ``AiCallbackHandler`` — credit and token accounting in ``AiLog``.
* ``recipe-from-source`` response shape — no new frontend.
"""

from __future__ import annotations

import traceback

import litellm
from cookbook.helper.ai_helper import AiCallbackHandler, can_perform_ai_request
from cookbook.models import AiLog, AiProvider, Recipe
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
from .vocabulary import (food_index, food_suggestions, keyword_index,
                         resolve_keywords, space_foods, space_units)

# Enough for a long page plus the schema and rules. Reasoning models spend
# part of this thinking; at 8000 Atlas measured an empty answer with
# finish_reason=length.
MAX_TOKENS = 16000


class ImportRequestSerializer(serializers.Serializer):
    url = serializers.CharField(required=False, allow_blank=True, max_length=2048)
    text = serializers.CharField(required=False, allow_blank=True)
    ai_provider_id = serializers.IntegerField()
    language = serializers.CharField(required=False, default='de', max_length=8)

    def validate(self, attrs):
        if not (attrs.get('url') or '').strip() and not (attrs.get('text') or '').strip():
            raise serializers.ValidationError('URL oder Text angeben')
        return attrs


def completion_model(name: str) -> str:
    """The model string litellm itself accepts for an OpenAI-compatible server.

    Tandoor stores a bare model name on its ``AiProvider`` (``atlas-recipe-global``,
    or ``llama3:8b`` for a local server). ``litellm.completion`` cannot route a
    bare name on its own -- it needs to be told which protocol to speak. The
    alias has no slash and is not a known provider, so it is prefixed with
    ``openai/``, which means "speak the OpenAI chat-completions protocol to the
    ``api_base`` given". Measured 2026-11-13: the bare name raised
    ``LLM Provider NOT provided``; the prefixed name answered through LiteLLM.

    The same measurement also caught a silent side effect: an unqualified name
    made LiteLLM create a Food and a Unit for every ingredient in the request.
    There is a test that counts them.
    """
    if '/' in name:
        return name
    return f'openai/{name}'


def _vocabulary(space) -> dict:
    """Everything the model may choose from, read once per request."""
    keywords = keyword_index(space)
    return {
        'foods': [f.name for f in space_foods(space)],
        'units': [u.name for u in space_units(space)],
        'tags': [k.name for k in keywords.values()],
        'food_index': food_index(space),
        'unit_index': {u.name.casefold().strip(): u for u in space_units(space)},
        'space': space,
    }


class FromSourceView(APIView):
    throttle_classes = [AiEndpointThrottle]
    permission_classes = [IsAuthenticated]

    def post(self, request, *args, **kwargs):
        serializer = ImportRequestSerializer(data=request.data)
        if not serializer.is_valid():
            return Response({'error': True, 'msg': serializer.errors},
                            status=status.HTTP_400_BAD_REQUEST)

        if not can_perform_ai_request(request.space):
            return Response({
                'error': True,
                'msg': _('AI ist für diesen Space ausgeschaltet oder das Guthaben ist aufgebraucht.'),
            }, status=status.HTTP_400_BAD_REQUEST)

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
                text, canonical = source.source_from_url(url)
                source_kind = 'url'
            else:
                text, canonical = source.source_from_text(serializer.validated_data['text']), ''
                source_kind = 'text'
        except source.FetchError as exc:
            return Response({'error': True, 'msg': str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        vocab = _vocabulary(request.space)
        messages = prompt.build_messages(
            text,
            source_kind=source_kind,
            known_foods=vocab['foods'],
            known_units=vocab['units'],
            known_tags=vocab['tags'],
            language=serializer.validated_data.get('language') or 'de',
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
        answer.setdefault('source_url', canonical)

        keywords, rejected_tags = resolve_keywords(request.space, answer.get('tags') or [])
        try:
            recipe = shaping.to_recipe_payload(
                answer,
                units=vocab['unit_index'],
                foods=vocab['food_index'],
                keywords=keywords,
            )
        except shaping.ShapeError as exc:
            return Response({'error': True, 'msg': f'Die AI-Antwort war unbrauchbar: {exc}'},
                            status=status.HTTP_422_UNPROCESSABLE_ENTITY)

        proposed_foods = [i.get('food') or '' for s in answer.get('steps') or []
                          for i in (s.get('ingredients') or []) if not i.get('is_header')]
        duplicates = []
        if canonical:
            with scopes_disabled():
                duplicates = list(Recipe.objects.filter(space=request.space, source_url=canonical)
                                  .values('id', 'name'))

        return Response({
            'recipe': recipe,
            'images': [],
            'duplicates': duplicates,
            'unknown_foods': food_suggestions(request.space, proposed_foods),
            'rejected_tags': rejected_tags,
        }, status=status.HTTP_200_OK)
