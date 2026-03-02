from django.db import models
from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.dispatch import receiver


class Profile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="profile")
    company = models.CharField(max_length=200, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Profile({self.user.username})"

    @property
    def active_plan(self):
        sub = self.user.subscription_set.filter(status="active").order_by("-created_at").first()
        if sub:
            return sub.plan
        return "free"

    @property
    def active_subscription(self):
        return self.user.subscription_set.filter(status="active").order_by("-created_at").first()


@receiver(post_save, sender=User)
def create_profile(sender, instance, created, **kwargs):
    if created:
        Profile.objects.create(user=instance)
