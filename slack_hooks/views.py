import json
import logging
import re
import urllib.parse

import slacker
from django.conf import settings
from django.db.models import Count, Q, Sum
from django.http import HttpResponse, HttpResponseBadRequest, HttpResponseForbidden, HttpResponseRedirect, JsonResponse
from django.shortcuts import render
from django.urls import reverse
from django.views.decorators.csrf import csrf_exempt

from flex_hours.utils import FlexNotEnabledException, calculate_flex_saldo
from invoices.models import Invoice, Project, TenkfUser

logger = logging.getLogger(__name__)  # pylint: disable=invalid-name
slack = slacker.Slacker(settings.SLACK_WORKSPACE_ACCESS_TOKEN)  # pylint:disable=invalid-name


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
            {
                "type": "button",
                "text": "10000ft",
                "url": "https://app.10000ft.com",
            },
        ],
    }
    return message, attachment


@csrf_exempt
def incoming_event(request):
    data = json.loads(request.body.decode("utf-8"))
    print(f"Incoming slack event: {data}")
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
                        "text": f"Flex saldo is not enabled for {person.full_name}.",
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
                tags = ", ".join([user.full_name for user in invoice.admin_users])
                unfurls[link["url"]] = {
                    "title": f"Solinor Invoice - {invoice.full_name} - {invoice.formatted_date}",
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
                            "value": tags or "-",
                        },
                        {
                            "title": "Incurred hours",
                            "short": True,
                            "value": f"{invoice.incurred_hours:.2f}h",
                        },
                        {
                            "title": "Incurred billing",
                            "short": True,
                            "value": f"{invoice.incurred_money:.2f}€",
                        },
                        {
                            "title": "Incorrect hour entries",
                            "short": True,
                            "value": invoice.incorrect_entries_count,
                        },
                    ],
                }

            projects_url = re.match(r"^/projects/([a-z0-9-]+)$", split_url.path)
            if projects_url:
                try:
                    project = Project.objects.get(guid=projects_url.group(1))
                except Project.DoesNotExist:
                    unfurls[link["url"]] = {
                        "text": "404 - project does not exist",
                    }
                    continue
                invoices = Invoice.objects.filter(project_m=project).exclude(Q(incurred_hours=0) & Q(incurred_money=0)).order_by("-year", "-month")
                message = ""
                if project.description:
                    message += project.description + "\n\n"
                total_incurred_hours = total_incurred_billing = 0
                if len(invoices):
                    for invoice in invoices:
                        total_incurred_hours += invoice.incurred_hours
                        total_incurred_billing += invoice.incurred_money

                    for c, invoice in enumerate(invoices):
                        if c > 12:
                            message += "..."
                            break
                        message += "- <https://{}{}|{} - {:.2f}h - {:.2f}€ - {}>\n".format(settings.DOMAIN, reverse("invoice", args=(invoice.invoice_id,)), invoice.formatted_date, invoice.incurred_hours, invoice.incurred_money, invoice.get_invoice_state_display())
                else:
                    message += "No invoices."
                unfurls[link["url"]] = {
                    "title": f"Solinor project - {project.full_name}",
                    "title_link": link["url"],
                    "text": message,
                    "mrkdwn_in": ["text"],
                    "fields": [
                        {
                            "title": "Start date",
                            "value": f"{project.starts_at:%Y-%m-%d}",
                            "short": True,
                        },
                        {
                            "title": "End date",
                            "value": f"{project.ends_at:%Y-%m-%d}",
                            "short": True,
                        },
                        {
                            "title": "Incurred hours",
                            "value": f"{total_incurred_hours:.2f}h",
                            "short": True,
                        },
                        {
                            "title": "Incurred billing",
                            "value": f"{total_incurred_billing:.2f}€",
                            "short": True,
                        },
                        {
                            "title": "Project state",
                            "value": project.project_state,
                            "short": True,
                        },
                    ],
                }

        if unfurls:
            print(f"Unfurl request: {unfurls}")
            try:
                slack.chat.unfurl(data["event"]["channel"], data["event"]["message_ts"], json.dumps(unfurls))
            except slacker.Error as err:
                print(f"An error occurred while unfurling: request={unfurls}, response={err}")
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
    if person.archived:
        return JsonResponse({
            "response_type": "ephemeral",
            "text": "You have been archived from 10000ft."
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
