from celery.utils.log import get_task_logger
from decouple import config
from django.core.exceptions import ObjectDoesNotExist

from property_management.models import Tenant, ArchivedTenant, Unit
from users.models import User

logger = get_task_logger(__name__)


def get_receipt_data(payment):
    """
  returns a dictionary comprising of the details for the payment
  """
    print("--------------------SENDING RECEIPT--------------------------")
    manager = User.objects.get(pk=payment["user"])
    manager_name = manager.first_name + " " + manager.last_name
    manager_email = manager.email

    try:
        tenant = Tenant.objects.get(tenant_slug=payment["tenant_slug"])
    except ObjectDoesNotExist as e:
        print(f"Exception as tenant is archived\n {e}")
        tenant = ArchivedTenant.objects.get(tenant_slug=payment["tenant_slug"])

    unit = Unit.objects.get(unit_slug=payment["unit"])
    unit_name = unit.unit_name
    prop = unit.property
    paid_invoices = []

    for item in payment["paid_invoices"]:
        item["invoice_date"] = format_date(item["invoice_date"])
        paid_invoices.append(dict(item))

    if payment["transaction_id"]:
        transaction_id = payment["transaction_id"]
    else:
        transaction_id = ""

    content = {
        "manager_name": manager_name,
        "manager_email": manager_email,
        "tenant_first_name": tenant.first_name,
        "tenant_last_name": tenant.last_name,
        "tenant_email": tenant.email,
        "tenant_phone": tenant.phone,
        "property_name": prop.property_name,
        "unit_name": unit_name,
        "date": format_date(payment["created_at"]),
        "amt_paid": payment["amt_paid"],
        "transaction_id": transaction_id,
        "paid_invoices": paid_invoices,
    }

    return content


def format_date(date):
    try:
        splitDate = date[:10].split("-")
        return splitDate[2] + "-" + splitDate[1] + "-" + splitDate[0]
    except Exception:
        return date.strftime("%d, %m, %Y").replace(", ", "-")
