import json
import logging

import slacker
from django.conf import settings
from django.http import HttpResponse, HttpResponseBadRequest, HttpResponseForbidden, HttpResponseRedirect, JsonResponse
from django.shortcuts import render
from django.urls import reverse
from django.views.decorators.csrf import csrf_exempt

from flex_hours.utils import calculate_flex_saldo
from invoices.models import TenkfUser

logger = logging.getLogger(__name__)  # pylint: disable=invalid-name
slack = slacker.Slacker(settings.SLACK_BOT_ACCESS_TOKEN)  # pylint:disable=invalid-name


@csrf_exempt
def incoming_event(request):
    data = json.loads(request.body.decode("utf-8"))
    logger.info("Incoming slack event: {}", data)
    if data.get("token") != settings.SLACK_VERIFICATION_TOKEN:
        return HttpResponseForbidden("Invalid verification token")
    if data.get("type") == "url_verification":
        return HttpResponse(data.get("challenge", ""), content_type="text/plain")
    if data.get("event"):
        for link in data["event"]["links"]:
            unfurl_request = {
                "channel": data["event"].get("channel"),
                "ts": data["event"].get("ts"),
                "unfurls": {
                    link["url"]: {
                        "text": "Test event",
                    },
                },
            }
            slack.chat.unfurl(unfurl_request)
        return HttpResponse("ok")


@csrf_exempt
def slack_query_flex_saldo(request):
    print("https://{}{}".format(settings.DOMAIN, reverse("your_flex_hours")))
    if not settings.SLACK_VERIFICATION_TOKEN or request.POST.get("token") != settings.SLACK_VERIFICATION_TOKEN:
        return HttpResponseForbidden("Invalid verification token")
    command = request.POST.get("command")
    user_id = request.POST.get("user_id")
    response_id = request.POST.get("response_url")

    if not user_id:
        return HttpResponseBadRequest("Invalid user_id - unable to process the request.")

    try:
        person = TenkfUser.objects.get(slack_id=user_id)
    except TenkfUser.DoesNotExist:
        return JsonResponse({
            "response_type": "ephemeral",
            "text": "Sorry, unable to fetch your flex saldo - user ID not found."
        })

    data = calculate_flex_saldo(person, only_active=True)
    if not data.get("active", True):
        return JsonResponse({
            "response_type": "ephemeral",
            "text": "It seems you don't have flex saldo activated right now.",
        })
    message = "Your flex saldo is {}h".format(data["cumulative_saldo"])
    if len(data["monthly_summary"]) > 1:
        change_since_last_month = "{:+.2f}h".format(data["cumulative_saldo"] - data["monthly_summary"][1]["cumulative_saldo"])
    else:
        change_since_last_month = "--"

    response = {
        "response_type": "ephemeral",
        "text": message,
        "attachments": [
            {
                "fields": [
                    {
                        "short": True,
                        "title": "Flex",
                        "value": "{:+.2f}h".format(data["cumulative_saldo"]),
                    },
                    {
                        "short": True,
                        "title": "KIKY deduction",
                        "value": "{:+.2f}h".format(data.get("kiky", {}).get("saldo", "?")),
                    },
                    {
                        "short": True,
                        "title": "Change from last month",
                        "value": change_since_last_month,
                    },
                ],
                "actions": [
                    {
                        "type": "button",
                        "style": "primary",
                        "text": "View details",
                        "url": "https://{}{}".format(settings.DOMAIN, reverse("your_flex_hours")),
                    },
                ],
            },
        ],
    }
    return JsonResponse(response)
