from django.db import models


class RPayBaseModel(models.Model):

    created_by = models.IntegerField(null=True)
    created_on = models.DateTimeField(auto_now_add=True)
    modified_by = models.IntegerField(null=True)
    modified_on = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True
