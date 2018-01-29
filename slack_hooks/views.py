import json
import logging
import re
import urllib.parse

import slacker
from django.conf import settings
from django.http import HttpResponse, HttpResponseBadRequest, HttpResponseForbidden, HttpResponseRedirect, JsonResponse
from django.shortcuts import render
from django.urls import reverse
from django.views.decorators.csrf import csrf_exempt

from flex_hours.utils import FlexNotEnabledException, calculate_flex_saldo
from invoices.models import Invoice, TenkfUser

logger = logging.getLogger(__name__)  # pylint: disable=invalid-name
slack = slacker.Slacker(settings.SLACK_BOT_ACCESS_TOKEN)  # pylint:disable=invalid-name


def get_slack_flex_response(person, ephemeral=True):
    data = calculate_flex_saldo(person, only_active=True)
    if not data.get("active", True):
        raise FlexNotEnabledException()
    message = "Flex saldo for {} is {:+.2f}h".format(person.full_name, data["cumulative_saldo"])
    if len(data["monthly_summary"]) > 1:
        change_since_last_month = "{:+.2f}h".format(data["cumulative_saldo"] - data["monthly_summary"][1]["cumulative_saldo"])
    else:
        change_since_last_month = "--"
    attachment = {
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
                "url": "https://{}{}".format(settings.DOMAIN, reverse("person_flex_hours", args=(person.guid,))),
            },
        ],
    }
    return message, attachment


@csrf_exempt
def incoming_event(request):
    data = json.loads(request.body.decode("utf-8"))
    print("Incoming slack event: {}".format(data))
    if data.get("token") != settings.SLACK_VERIFICATION_TOKEN:
        return HttpResponseForbidden("Invalid verification token")
    if data.get("type") == "url_verification":
        return HttpResponse(data.get("challenge", ""), content_type="text/plain")
    if data.get("event"):
        unfurls = {}
        for link in data["event"]["links"]:
            split_url = urllib.parse.urlsplit(link["url"])
            unfurl_request = None
            flex_hours_path = re.match(r"^/users/([a-z0-9-]+)/flexhours", split_url.path)
            if flex_hours_path:
                try:
                    person = TenkfUser.objects.get(guid=flex_hours_path.group(1))
                except TenkfUser.DoesNotExist:
                    unfurls[link["url"]] = {
                        "text": "404 - User does not exist",
                    }
                    continue
                try:
                    message, attachment = get_slack_flex_response(person)
                except FlexNotEnabledException:
                    unfurls[link["url"]] = {
                        "text": "Flex saldo is not enabled for {}.".format(person.full_name),
                    }
                    continue
                attachment["text"] = message
                attachment["is_app_unfurl"] = True
                unfurls[link["url"]] = attachment
            invoice_url = re.match(r"^/invoices/([a-z0-9-]+)$", split_url.path)
            if invoice_url:
                try:
                    invoice = Invoice.objects.get(invoice_id=invoice_url.group(1))
                except Invoice.DoesNotExist:
                    unfurls[link["url"]] = {
                        "text": "404 - this invoice does not exist",
                    }
                    continue
                unfurls[link["url"]] = {
                    "title": "Solinor Invoice - {} - {}".format(invoice.full_name, invoice.date),
                    "title_link": link["url"],
                    "fields": [
                        {
                            "title": "Invoice state",
                            "short": True,
                            "value": invoice.get_invoice_state_display(),
                        },
                        {
                            "title": "Tags",
                            "short": True,
                            "value": invoice.tags,
                        },
                        {
                            "title": "Incurred hours",
                            "short": True,
                            "value": "{:.2f}h".format(invoice.incurred_hours),
                        },
                        {
                            "title": "Incurred billing",
                            "short": True,
                            "value": "{:.2f}€".format(invoice.incurred_money),
                        },
                        {
                            "title": "Incorrect hour entries",
                            "short": True,
                            "value": invoice.incorrect_entries_count,
                        },
                    ],
                }

        if unfurls:
            print("Unfurl request: {}".format(unfurls))
            try:
                slack.chat.unfurl(data["event"]["channel"], data["event"]["message_ts"], json.dumps(unfurls))
            except slacker.Error as err:
                print("An error occurred while unfurling: request={}, response={}".format(unfurls, err))
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

    try:
        message, attachment = get_slack_flex_response(person)
    except FlexNotEnabledException:
        return JsonResponse({
            "response_type": "ephemeral",
            "text": "It seems you don't have flex saldo activated right now.",
        })
    response = {
        "response_type": "ephemeral",
        "text": message,
        "attachments": [
            attachment
        ],
    }
    return JsonResponse(response)
