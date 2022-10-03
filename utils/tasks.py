import base64
import socket
import requests
from random import randint

import africastalking as at
from celery import shared_task
from celery.utils.log import get_task_logger
from decouple import config
from django.conf import settings
from django.template import loader
import python_http_client
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import (
    Mail,
    From,
    To,
    Subject,
    HtmlContent,
    Attachment,
    FileContent,
    FileName,
    FileType,
    Disposition,
    PlainTextContent,
)
from weasyprint import HTML

from invoices.utils import get_invoice_data, generate_invoice_pdf
from property_management.models import Property, Tenant, Unit
from users.models import User
from utils.mailer import get_receipt_data

logger = get_task_logger(__name__)
at.initialize(config("AT_USERNAME"), config("AT_API_KEY"))

# init sms service
sms = at.SMS

sg = SendGridAPIClient(
    "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"
)


def get_balance():
    if not settings.DEBUG:
        balance_url = (
            f"https://api.africastalking.com/version1/user?username={config('AT_USERNAME')}"
        )
        headers = {"Accept": "application/json", "apiKey": config("AT_API_KEY")}

        try:
            response = requests.get(balance_url, headers=headers)
            response = response.json()
            balance = float(response["UserData"]["balance"].split()[1])
            return balance
        except requests.exceptions.RequestException as e:
            logger.error(f'Failed to get africastalking balance: {str(e)}')
    else:
        logger.debug('Skipped getting africastalking balance as worker process is running in DEBUG mode')


def to_international(number):
    # check other number formats and set to appropriate international format
    if number[0] == "0":
        number = f"+254{number[1:]}"
    elif number[0] == "7":
        number = f"+254{number}"
    return number


def send_sms(msg, receipients):
    if type(receipients) is list:
        receipients = [to_international(number) for number in receipients]
    else:
        receipients = list(receipients)
        receipients = [to_international(number) for number in receipients]

    sms.send(msg, receipients, sender_id="RENTPAY")


@shared_task
def withdrawal_notification(data):
    logger.debug("--------------------SENDING WITHDRAWAL SMS--------------------------")
    msg = f"Hi {data['name']}. Your withdrawal request for {data['amount']} to {data['property_name']}\
  account {data['account_name']} account no. {data['account_no']} was successful.\
  The funds will be credited to your account within 24hrs."

    receipients = [data["phone"]]
    send_sms(msg, receipients)
    logger.info('Withdraw SMS successfully sent')


@shared_task
def email_sender(content, email_type, pdf_path=None):
    """Sends email given content, email type and attachment path"""
    subject = None
    sent_from = config("EMAIL_USER")
    if email_type == "ONBOARDING":
        content["tenant_email"] = content["email"]
        send_to = content["email"]
        subject = "Welcome to RentPay"
        html_content = loader.render_to_string("new_user_email.html", content)

    if email_type == "TENANT":
        content["tenant_email"] = content["email"]
        prop = Property.objects.select_related("user").get(
            id=content["assigned_property_id"]
        )
        tenant = (
            Tenant.objects.filter(assigned_property_id=content["assigned_property_id"])
            .order_by("-id")
            .first()
        )
        unit_slug = content["assigned_unit"]
        unit = Unit.objects.get(unit_slug=unit_slug)
        content["unit_name"] = unit.unit_name
        content["tenant_reference"] = tenant.tenant_reference
        content["landlord"] = f"{prop.user.first_name} {prop.user.last_name}"
        content["property_name"] = prop.property_name
        content["name"] = f"{content['first_name']} {content['last_name']}"
        send_to = content["email"]
        subject = "Welcome to RentPay"
        html_content = loader.render_to_string("tenant_email.html", content)

    if email_type == "INVOICE":
        send_to = content["tenant_email"]
        subject = "Late Payment Notice" if content.get("delayed") else "Rent Invoice"
        html_content = loader.render_to_string("invoice_email.html", content)

    if email_type == "MPESA_RECEIPT" or email_type == "RECEIPT":
        send_to = content["tenant_email"]
        subject = "Rent Receipt"
        html_content = loader.render_to_string("receipt_email.html", content)

    if email_type == "WITHDRAWAL":
        send_to = [
            To("david.kimani@rentpay.africa"),
            To("christabel.ojuok@rentpay.africa"),
        ]
        subject = "User wallet withdrawal"
        message = Mail(
            from_email=From(sent_from),
            to_emails=send_to,
            subject=Subject(subject),
            plain_text_content=PlainTextContent(content["mail"]),
        )

        try:
            sg.send(message)
        except Exception as e:
            logger.error(f'Error encountered sending {email_type} email via sendgrid: {str(e)}')
            pass

        withdrawal_notification.delay(content)

        return

    if email_type == "RENTPAY":
        send_to = [To("david.kimani@rentpay.africa"), To("hello@rentpay.africa")]
        subject = "New Lead Sign-up!"
        html_content = loader.render_to_string("new_lead_email.html", content)

    if email_type == "LEADS":
        send_to = content["email"]
        subject = "RentPay Demo Scheduled"
        html_content = loader.render_to_string("lead_email.html", content)

    message = Mail(
        from_email=From(sent_from),
        to_emails=send_to,
        subject=Subject(subject),
        html_content=HtmlContent(html_content),
    )

    if pdf_path:
        with open(pdf_path, "rb") as f:
            data = f.read()

        encoded_file = base64.b64encode(data).decode()
        attachedFile = Attachment(
            FileContent(encoded_file),
            FileName(f"{email_type}.pdf"),
            FileType("application/pdf"),
            Disposition("attachment"),
        )

        message.attachment = attachedFile

    try:
        sg.send(message)
    except python_http_client.exceptions.HTTPError as e:
        logger.error(f'Error encountered sending {email_type} email via sendgrid: {str(e)}')
        return


@shared_task
def send_receipt(payment, receipients):
    logger.debug("--------------------SENDING RECEIPT SMS--------------------------")
    msg = f"Hi {payment['name']}, your payment of Ksh.{payment['amt_paid']}\
  for Hse No. {payment['unit_name']} at\
  {payment['property_name']} was successful!"

    send_sms(msg, receipients)


@shared_task
def send_tenant_reference(details):
    msg = f"Hi {details['tenant_name']}. Your reference {details['agency_tenant_reference']} for rent payment to {details['landlord_details'][0]['bank_account_name']}, {details['landlord_details'][0]['bank_name']}, {details['landlord_details'][0]['bank_account_number']} is in progress for {details['property_name']} {details['house_number']}. Please confirm the bank details are correct."
    send_sms(msg, [details["phone_number"]])


@shared_task
def send_tenant_collection(details):
    msg = f"Hi {details['tenant']['name']}. Rent payment of Ksh {details['amount']} for {details['property_name']} {details['house_number']} was successful to {details['account_name']} {details['bank_name']}, {details['account_no']}. Transaction fee {details['fee']}"
    send_sms(msg, [details["tenant"]["phone_number"]])


@shared_task
def send_agent_collection(details):
    msg = f"Hi {details['agent']['name']}. Rent payment of Ksh {details['amount']} for {details['property_name']} {details['house_number']} was successful to {details['account_name']} {details['bank_name']}, {details['account_no']}. Transaction fee Ksh {details['fee']}. Commission ksh {details['commission']}"
    send_sms(msg, [details["agent"]["phone_number"]])


@shared_task
def send_landlord_collection(details):
    msg = f"Hi. Rent payment has been sent from {details['tenant']['name']} of Ksh {details['amount']} for {details['property_name']} {details['house_number']} to {details['bank_name']}, {details['account_no']}. You can easily manage your property for online on rentpay.africa"
    send_sms(msg, [details["landlord"]["phone_number"]])


@shared_task
def send_invoice_sms(data):
    logger.debug("--------------------SENDING INVOICE SMS--------------------------")
    payment = get_invoice_data(data)
    msg = f"Hi {payment['tenant_name']}, find your invoice {payment['invoice_no']} of Kshs.{payment['invoice_total']} for Hse No {payment['unit_name']} in {payment['property_name']}.\
  \nClick the link to pay {payment['mobile_link']} or pay to Paybill {payment['paybill']['mpesa_paybill']} and enter your RentPay Reference as {payment['tenant_reference']}."

    if not payment["paybill"]["is_active"]:
        msg = f"Hi {payment['tenant_name']}, find your invoice {payment['invoice_no']} of Kshs.{payment['invoice_total']} for Hse No {payment['unit_name']} in {payment['property_name']}.\
  Click the link to view invoice {payment['mobile_link']}"

    send_sms(msg, [payment["tenant_phone"]])


@shared_task
def send_lead_sms(data):
    logger.debug("--------------------SENDING LEAD SMS--------------------------")
    name = f"{data['first_name']} {data['last_name']}"
    msg = f"Hi {name}. You have successfully registered to RentPay with a FREE 30 day trial.\
  Your demo is scheduled for {data['demo_date']}. Click here to login {data['link']}."

    send_sms(msg, [data["phone"]])


@shared_task
def send_onboarding_sms(data, signed=None):
    logger.debug("--------------------SENDING ONBOARDING SMS--------------------------")
    name = f"{data['first_name']} {data['last_name']}"
    msg = f"Hi {name}.\nYou have successfully registered to RentPay with a FREE 30 day trial.\nClick here to login {data['link']}"

    if signed:
        user = User.objects.get(id=data["created_by"])
        admin = f"{user.first_name} {user.last_name}"
        msg = f"Hi {name}.\nYou have been successfully registered as a {data['role']} on RentPay by {admin}. Click here to login {data['link']}"

    send_sms(msg, [data["phone"]])


@shared_task
def send_tenant_sms(data, unit):
    logger.debug("--------------------SENDING TENANT SMS--------------------------")
    prop = Property.objects.select_related("user").get(id=data["assigned_property_id"])
    tenant = (
        Tenant.objects.filter(assigned_property_id=data["assigned_property_id"])
        .order_by("-id")
        .first()
    )
    name = f"{data['first_name']} {data['last_name']}"
    msg = f"Hi {name}. You have been registered on RentPay by {prop.user.first_name}\
  {prop.user.last_name} as a tenant in {prop.property_name} , Hse No {unit}.\
  Your Reference Number is {tenant.tenant_reference}.\
  Use this reference when making rent payments from today. Reach out to your landlord or agent for confirmation."

    send_sms(msg, [data["phone"]])


@shared_task
def sms_onboarding_procees(receipients):
    logger.debug("--------------------SENDING ACTIVATION SMS--------------------------")
    msg = f"Hi. You signed up on RentPay but have not logged in.\
  Please follow the link {config('FRONTEND_DOMAIN')} to finish setting up your account.\
  In case of assistance reach out on 0743466209 or hello@rentpay.africa"

    send_sms(msg, receipients)


@shared_task
def send_delayed_invoice(data):
    logger.debug("--------------------SENDING DELAYED SMS--------------------------")
    payment = get_invoice_data(data)
    msg = f"Hi {data['tenant']}, this is a reminder to clear the balance of Kshs.{data['amt_due']} on invoice\
  {data['invoice_no']} for Hse No. {payment['unit_name']} at {payment['property_name']}.\
  Please click the link to make payment {payment['mobile_link']}"

    if payment["paybill"]:
        msg = f"{msg} to paybill {payment['paybill']['mpesa_paybill']}."

    send_sms(msg, [payment["tenant_phone"]])


@shared_task
def send_otp(data):
    logger.debug("--------------------SENDING OTP SMS--------------------------")
    msg = f"Your verification code is {data['otp']}. Do not share this with anyone."

    send_sms(msg, [data["phone"]])


@shared_task
def send_email(invoice_json, email_type):
    """Generates pdf then sends email"""
    # Rendered
    if email_type == "INVOICE":

        data = generate_invoice_pdf(invoice_json)
        path_name = data["path_name"]
        email_content = data["content"]

        # send mail
        try:
            email_sender(email_content, email_type, path_name)
        except socket.gaierror:
            return

    elif email_type == "RECEIPT":
        content = get_receipt_data(invoice_json)
        html_string = loader.render_to_string("receipt.html", content)
        html = HTML(string=html_string)
        loc = f"/tmp/rentpay/receipts/rent_receipt_{randint(0,1000)}.pdf"
        html.write_pdf(target=loc)

        # send mail
        try:
            email_sender(content, email_type, loc)
        except socket.gaierror:
            return


@shared_task
def check_africastalking_balance(threshold=500.0):
    balance = get_balance()
    if balance <= threshold:
        msg = f"Hello David,\n the AfricasTalking balance for RentPay is currently below {threshold}. Please top up account."
        send_sms(msg, ["0735133558"])
        message = Mail(
            from_email=config("EMAIL_USER"),
            to_emails="david.kimani@rentpay.africa",
            subject="RentPay SMS balance is low",
            plain_text_content=PlainTextContent(msg),
        )
        try:
            sg.send(message)
        except python_http_client.exceptions.HTTPError as e:
            logger.error(f'Error encountered sending email via sendgrid: {str(e)}')
