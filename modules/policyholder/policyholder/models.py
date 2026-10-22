
from contribution_plan.models import ContributionPlanBundle
from django.conf import settings
from django.db import models
from core import models as core_models
from graphql import GraphQLResolveInfo as ResolveInfo
from location.models import Location, LocationManager
from insuree.models import Insuree
from policy.models import Policy


class PolicyHolderManager(core_models.HistoryModelManager):
    def filter(self, *args, **kwargs):
        keys = [x for x in kwargs if "itemsvc" in x]
        for key in keys:
            new_key = key.replace("itemsvc", self.model.model_prefix)
            kwargs[new_key] = kwargs.pop(key)
        return super(PolicyHolderManager, self).filter(*args, **kwargs)


class PolicyHolder(core_models.HistoryBusinessModel):
    code = models.CharField(db_column='PolicyHolderCode', max_length=32)
    trade_name = models.CharField(db_column='TradeName', max_length=255)
    locations = models.ForeignKey(Location, db_column='LocationsId', on_delete=models.deletion.DO_NOTHING, blank=True, null=True)
    address = models.JSONField(db_column='Address', blank=True, null=True)
    phone = models.CharField(db_column='Phone', max_length=16, blank=True, null=True)
    fax = models.CharField(db_column='Fax', max_length=16, blank=True, null=True)
    email = models.CharField(db_column='Email', max_length=255, blank=True, null=True)
    contact_name = models.JSONField(db_column='ContactName', blank=True, null=True)
    legal_form = models.IntegerField(db_column='LegalForm', blank=True, null=True)
    activity_code = models.IntegerField(db_column='ActivityCode', blank=True, null=True)
    accountancy_account = models.CharField(db_column='AccountancyAccount', max_length=64, blank=True, null=True)
    bank_account = models.JSONField(db_column="bankAccount", blank=True, null=True)
    payment_reference = models.CharField(db_column='PaymentReference', max_length=128, blank=True, null=True)

    objects = PolicyHolderManager()

    @classmethod
    def get_queryset(cls, queryset, user):
        queryset = cls.filter_queryset(queryset)
        if isinstance(user, ResolveInfo):
            user = user.context.user
        if settings.ROW_SECURITY and user.is_anonymous:
            return queryset.filter(id=None)
        if settings.ROW_SECURITY:
            return LocationManager().build_user_location_filter_query(user._u, queryset=queryset, prefix='locations')
        return queryset

    class Meta:
        db_table = 'tblPolicyHolder'


class PolicyHolderInsureeManager(core_models.HistoryModelManager):
    def filter(self, *args, **kwargs):
        keys = [x for x in kwargs if "itemsvc" in x]
        for key in keys:
            new_key = key.replace("itemsvc", self.model.model_prefix)
            kwargs[new_key] = kwargs.pop(key)
        return super(PolicyHolderInsureeManager, self).filter(*args, **kwargs)


class PolicyHolderInsuree(core_models.HistoryBusinessModel):
    policy_holder = models.ForeignKey(PolicyHolder, db_column='PolicyHolderId',
                                      on_delete=models.deletion.DO_NOTHING)
    insuree = models.ForeignKey(Insuree, db_column='InsureeId',
                                on_delete=models.deletion.DO_NOTHING)
    contribution_plan_bundle = models.ForeignKey(ContributionPlanBundle, db_column='ContributionPlanBundleId',
                                                 on_delete=models.deletion.DO_NOTHING, blank=True, null=True)
    last_policy = models.ForeignKey(Policy, db_column='LastPolicyId', on_delete=models.deletion.DO_NOTHING, blank=True, null=True)

    objects = PolicyHolderInsureeManager()

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
        db_table = 'tblPolicyHolderInsuree'


class PolicyHolderContributionPlanManager(core_models.HistoryModelManager):
    def filter(self, *args, **kwargs):
        keys = [x for x in kwargs if "itemsvc" in x]
        for key in keys:
            new_key = key.replace("itemsvc", self.model.model_prefix)
            kwargs[new_key] = kwargs.pop(key)
        return super(PolicyHolderContributionPlanManager, self).filter(*args, **kwargs)


class PolicyHolderContributionPlan(core_models.HistoryBusinessModel):
    policy_holder = models.ForeignKey(PolicyHolder, db_column='PolicyHolderId',
                                      on_delete=models.deletion.DO_NOTHING)
    contribution_plan_bundle = models.ForeignKey(ContributionPlanBundle, db_column='ContributionPlanBundleId',
                                                 on_delete=models.deletion.DO_NOTHING)

    objects = PolicyHolderContributionPlanManager()

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
        db_table = 'tblPolicyHolderContributionPlan'


class PolicyHolderUserManager(core_models.HistoryModelManager):
    def filter(self, *args, **kwargs):
        keys = [x for x in kwargs if "itemsvc" in x]
        for key in keys:
            new_key = key.replace("itemsvc", self.model.model_prefix)
            kwargs[new_key] = kwargs.pop(key)
        return super(PolicyHolderUserManager, self).filter(*args, **kwargs)


class PolicyHolderUser(core_models.HistoryBusinessModel):
    user = models.ForeignKey(
        core_models.User,
        db_column='UserID',
        on_delete=models.deletion.DO_NOTHING
    )
    policy_holder = models.ForeignKey(PolicyHolder, db_column='PolicyHolderId',
                                      on_delete=models.deletion.DO_NOTHING)

    objects = PolicyHolderUserManager()

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
        db_table = 'tblPolicyHolderUser'


class PolicyHolderMutation(core_models.UUIDModel, core_models.ObjectMutation):
    policy_holder = models.ForeignKey(
        PolicyHolder,
        models.DO_NOTHING,
        related_name='mutations'
    )
    mutation = models.ForeignKey(
        core_models.MutationLog, models.DO_NOTHING, related_name='policy_holder')

    class Meta:
        managed = True
        db_table = "policy_holder_PolicyHolderMutation"


class PolicyHolderInsureeMutation(core_models.UUIDModel):
    policy_holder_insuree = models.ForeignKey(
        PolicyHolderInsuree,
        models.DO_NOTHING,
        related_name='mutations'
    )
    mutation = models.ForeignKey(
        core_models.MutationLog, models.DO_NOTHING, related_name='policy_holder_insuree')

    class Meta:
        managed = True
        db_table = "policy_holder_insuree_PolicyHolderInsureeMutation"


class PolicyHolderContributionPlanMutation(core_models.UUIDModel):
    policy_holder_contribution_plan = models.ForeignKey(
        PolicyHolderContributionPlan,
        models.DO_NOTHING,
        related_name='mutations'
    )
    mutation = models.ForeignKey(
        core_models.MutationLog,
        models.DO_NOTHING,
        related_name='policy_holder_contribution_plan'
    )

    class Meta:
        managed = True
        db_table = "policy_holder_contribution_plan_PolicyHolderContributionPlanMutation"


class PolicyHolderUserMutation(core_models.UUIDModel):
    policy_holder_user = models.ForeignKey(
        PolicyHolderUser, models.DO_NOTHING,
        related_name='mutations'
    )
    mutation = models.ForeignKey(
        core_models.MutationLog, models.DO_NOTHING, related_name='policy_holder_user')

    class Meta:
        managed = True
        db_table = "policy_holder_user_PolicyHolderUserMutation"


def has_hybrid_phu_perms(user, ph, perms):
    if user.has_perms(perms):
        # TODO make cache
        return PolicyHolderUser.objects.filter(policy_holder=ph, user=user).exists()
    return False
