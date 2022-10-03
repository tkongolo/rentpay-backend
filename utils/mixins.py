from django.db import models


class TimestampMixin(models.Model):
    """
    An abstract base class model that adds timestamps on record creation and update
    """
    created_on = models.DateTimeField(editable=False, db_index=True, auto_now_add=True)
    modified_on = models.DateTimeField(editable=False, db_index=True, auto_now=True)

    class Meta:
        abstract = True


class UserMixin(models.Model):
    """
    An abstract base class model that adds user information on creation and update
    """

    created_by = models.ForeignKey(
        'users.User', editable=False, blank=True, null=True,
        on_delete=models.PROTECT, related_name='created_by_%(class)ss'
    )
    modified_by = models.ForeignKey(
        'users.User', editable=False, blank=True, null=True,
        on_delete=models.PROTECT, related_name='updated_by_%(class)ss')

    class Meta:
        abstract = True

