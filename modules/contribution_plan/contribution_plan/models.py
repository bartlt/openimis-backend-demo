from django.conf import settings
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models
from core import models as core_models, fields
from core.signals import Signal
from graphql import GraphQLResolveInfo as ResolveInfo
from contribution_plan.mixins import GenericPlanQuerysetMixin, GenericPlanManager


class GenericPlan(GenericPlanQuerysetMixin, core_models.HistoryBusinessModel):
    code = models.CharField(db_column="Code", max_length=255, blank=True, null=True)
    name = models.CharField(db_column="Name", max_length=255, blank=True, null=True)
    calculation = models.UUIDField(db_column="calculationUUID", null=False)
    benefit_plan_id = models.CharField(db_column="BenefitPlanID", max_length=255, blank=True, null=True)
    benefit_plan_type = models.ForeignKey(ContentType, db_column="BenefitPlanType", on_delete=models.DO_NOTHING, null=True, unique=False)
    benefit_plan = GenericForeignKey('benefit_plan_type', 'benefit_plan_id')
    periodicity = models.IntegerField(db_column="Periodicity", null=False)

    objects = GenericPlanManager()

    class Meta:
        abstract = True


class ContributionPlanBundleManager(models.Manager):
    def filter(self, *args, **kwargs):
        keys = [x for x in kwargs if "itemsvc" in x]
        for key in keys:
            new_key = key.replace("itemsvc", self.model.model_prefix)
            kwargs[new_key] = kwargs.pop(key)
        return super(ContributionPlanBundleManager, self).filter(*args, **kwargs)


class ContributionPlanBundle(core_models.HistoryBusinessModel):
    code = models.CharField(db_column='Code', max_length=255, null=False)
    name = models.CharField(db_column='Name', max_length=255, blank=True, null=True)
    periodicity = models.IntegerField(db_column="Periodicity", blank=True, null=True)

    objects = ContributionPlanBundleManager()

    @classmethod
    def get_queryset(cls, queryset, user):
        queryset = cls.filter_queryset(queryset)
        if isinstance(user, ResolveInfo):
            user = user.context.user
        if settings.ROW_SECURITY and user.is_anonymous:
            return queryset.filter(id=None)
        if settings.ROW_SECURITY:
            pass
        return queryset

    class Meta:
        db_table = 'tblContributionPlanBundle'


class ContributionPlanManager(models.Manager):
    def filter(self, *args, **kwargs):
        keys = [x for x in kwargs if "itemsvc" in x]
        for key in keys:
            new_key = key.replace("itemsvc", self.model.model_prefix)
            kwargs[new_key] = kwargs.pop(key)
        return super(ContributionPlanManager, self).filter(*args, **kwargs)


class ContributionPlan(GenericPlan):


    class Meta:
        db_table = 'tblContributionPlan'

class PaymentPlan(GenericPlan):

    class Meta:
        db_table = 'tblPaymentPlan'


class ContributionPlanBundleDetailsManager(models.Manager):
    def filter(self, *args, **kwargs):
        keys = [x for x in kwargs if "itemsvc" in x]
        for key in keys:
            new_key = key.replace("itemsvc", self.model.model_prefix)
            kwargs[new_key] = kwargs.pop(key)
        return super(ContributionPlanBundleDetailsManager, self).filter(*args, **kwargs)


class ContributionPlanBundleDetails(core_models.HistoryBusinessModel):
    contribution_plan_bundle = models.ForeignKey(ContributionPlanBundle, db_column="ContributionPlanBundleUUID",
                                                 on_delete=models.deletion.DO_NOTHING)
    contribution_plan = models.ForeignKey(ContributionPlan, db_column="ContributionPlanUUID",
                                          on_delete=models.deletion.DO_NOTHING)

    objects = ContributionPlanBundleDetailsManager()

    @classmethod
    def get_queryset(cls, queryset, user):
        queryset = cls.filter_queryset(queryset)
        if isinstance(user, ResolveInfo):
            user = user.context.user
        if settings.ROW_SECURITY and user.is_anonymous:
            return queryset.filter(id=None)
        if settings.ROW_SECURITY:
            pass
        return queryset

    class Meta:
        db_table = 'tblContributionPlanBundleDetails'


class ContributionPlanMutation(core_models.UUIDModel):
    contribution_plan = models.ForeignKey(ContributionPlan, models.DO_NOTHING,
                                 related_name='mutations')
    mutation = models.ForeignKey(
        core_models.MutationLog, models.DO_NOTHING, related_name='contribution_plan')

    class Meta:
        managed = True
        db_table = "contribution_plan_ContributionPlanMutation"


class ContributionPlanBundleMutation(core_models.UUIDModel, core_models.ObjectMutation):
    contribution_plan_bundle = models.ForeignKey(ContributionPlanBundle, models.DO_NOTHING,
                                 related_name='mutations')
    mutation = models.ForeignKey(
        core_models.MutationLog, models.DO_NOTHING, related_name='contribution_plan_bundle')

    class Meta:
        managed = True
        db_table = "contribution_plan_bundle_ContributionPlanBundleMutation"
