from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone


CONTENT_TYPES = [
    ("blog_post", "Blog Post"),
    ("product_description", "Product Description"),
    ("ad_copy", "Ad Copy"),
    ("email_sequence", "Email Sequence"),
]

GENERATION_STATUS = [
    ("queued", "Queued"),
    ("running", "Running"),
    ("success", "Success"),
    ("failed", "Failed"),
]

TONE_CHOICES = [
    ("professional", "Professional"),
    ("casual", "Casual"),
    ("witty", "Witty"),
    ("formal", "Formal"),
    ("persuasive", "Persuasive"),
]


class Project(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="projects")
    name = models.CharField(max_length=200)
    brand_name = models.CharField(max_length=200)
    tone = models.CharField(max_length=50, choices=TONE_CHOICES, default="professional")
    audience = models.TextField(help_text="Describe your target audience")
    keywords = models.TextField(help_text="Comma-separated keywords")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["user", "created_at"])]

    def __str__(self):
        return f"{self.name} ({self.user.username})"

    def keyword_list(self):
        return [k.strip() for k in self.keywords.split(",") if k.strip()]


class ContentGeneration(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="generations")
    project = models.ForeignKey(
        Project, on_delete=models.CASCADE, related_name="generations"
    )
    content_type = models.CharField(max_length=50, choices=CONTENT_TYPES)
    prompt_extra = models.TextField(blank=True, help_text="Extra instructions")
    status = models.CharField(max_length=20, choices=GENERATION_STATUS, default="queued")
    result_text = models.TextField(blank=True)
    word_count = models.PositiveIntegerField(default=0)
    error_message = models.TextField(blank=True)
    celery_task_id = models.CharField(max_length=200, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["user", "status"]),
            models.Index(fields=["project", "created_at"]),
        ]

    def __str__(self):
        return f"Gen({self.content_type}, {self.status})"


class UsageLedger(models.Model):
    """Tracks word usage per user per calendar month."""

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="usage_ledgers")
    year = models.PositiveSmallIntegerField()
    month = models.PositiveSmallIntegerField()
    words_used = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [("user", "year", "month")]
        indexes = [models.Index(fields=["user", "year", "month"])]

    def __str__(self):
        return f"Usage({self.user.username}, {self.year}-{self.month:02d}, {self.words_used}w)"

    @classmethod
    def current_for(cls, user):
        now = timezone.now()
        obj, _ = cls.objects.get_or_create(
            user=user, year=now.year, month=now.month, defaults={"words_used": 0}
        )
        return obj
