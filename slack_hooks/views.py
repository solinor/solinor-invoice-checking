import json
import logging

from django.conf import settings
from django.http import HttpResponse, HttpResponseBadRequest, HttpResponseForbidden, HttpResponseRedirect
from django.shortcuts import render
from django.views.decorators.csrf import csrf_exempt

logger = logging.getLogger(__name__)  # pylint: disable=invalid-name


@csrf_exempt
def incoming_event(request):
    data = json.loads(request.body.decode("utf-8"))
    logger.info("Incoming slack event: {}", data)
    if data.get("type") == "url_verification":
        if data.get("token") != settings.SLACK_VERIFICATION_TOKEN:
            return HttpResponseForbidden("Invalid verification token")
        return HttpResponse(data.get("challenge", ""), content_type="text/plain")
