from sys import stderr
from decouple import config

from sendgrid import SendGridAPIClient


def send_sendgrid_mail(data):
    """
  Sends emails through sendgrid API using a dynamic template setup in sendgrid.\n
  Requires email data to be passed
  """
    try:
        sg = SendGridAPIClient(config("SENDGRID_API_KEY"))
        response = sg.client.mail.send.post(request_body=data)
        print(response.status_code)
        print(response.body)
        print(response.headers)
    except Exception as e:
        print(e)
        stderr.write("Status : FAIL, message %s" % e)
