"""
Tests for quota enforcement, usage deduction, and rate limiting.
"""
from unittest.mock import MagicMock, patch

from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone

from apps.billing.models import Subscription
from apps.content.models import ContentGeneration, Project, UsageLedger
from apps.content.services import (
    check_project_limit,
    check_quota,
    deduct_usage,
    enqueue_generation,
    usage_summary,
)


def make_user(username="testuser"):
    return User.objects.create_user(username=username, email=f"{username}@test.com", password="pw")


def make_project(user):
    return Project.objects.create(
        user=user,
        name="Test Project",
        brand_name="TestBrand",
        tone="professional",
        audience="Developers",
        keywords="python, django",
    )


class QuotaCheckTests(TestCase):
    def setUp(self):
        self.user = make_user()

    def test_free_user_under_limit_allowed(self):
        ok, msg = check_quota(self.user)
        self.assertTrue(ok)
        self.assertEqual(msg, "")

    def test_free_user_at_limit_denied(self):
        now = timezone.now()
        UsageLedger.objects.create(
            user=self.user, year=now.year, month=now.month, words_used=5_000
        )
        ok, msg = check_quota(self.user)
        self.assertFalse(ok)
        self.assertIn("Monthly word limit", msg)

    def test_pro_user_at_free_limit_still_allowed(self):
        """Pro users have 60k limit; 5k used should still be allowed."""
        now = timezone.now()
        Subscription.objects.create(
            user=self.user,
            plan="pro",
            status="active",
            current_period_end=now + timezone.timedelta(days=30),
        )
        UsageLedger.objects.create(
            user=self.user, year=now.year, month=now.month, words_used=5_000
        )
        ok, msg = check_quota(self.user)
        self.assertTrue(ok)

    def test_pro_user_at_pro_limit_denied(self):
        now = timezone.now()
        Subscription.objects.create(
            user=self.user,
            plan="pro",
            status="active",
            current_period_end=now + timezone.timedelta(days=30),
        )
        UsageLedger.objects.create(
            user=self.user, year=now.year, month=now.month, words_used=60_000
        )
        ok, msg = check_quota(self.user)
        self.assertFalse(ok)


class ProjectLimitTests(TestCase):
    def setUp(self):
        self.user = make_user()

    def test_free_user_under_project_limit(self):
        ok, _ = check_project_limit(self.user)
        self.assertTrue(ok)

    def test_free_user_at_project_limit(self):
        for i in range(3):
            make_project(self.user)
        ok, msg = check_project_limit(self.user)
        self.assertFalse(ok)
        self.assertIn("Project limit", msg)

    def test_pro_user_can_create_more_projects(self):
        now = timezone.now()
        Subscription.objects.create(
            user=self.user,
            plan="pro",
            status="active",
            current_period_end=now + timezone.timedelta(days=30),
        )
        for i in range(3):
            make_project(self.user)
        ok, _ = check_project_limit(self.user)
        self.assertTrue(ok)


class DeductUsageTests(TestCase):
    def setUp(self):
        self.user = make_user()

    def test_deduct_creates_ledger_if_absent(self):
        deduct_usage(self.user, 100)
        now = timezone.now()
        ledger = UsageLedger.objects.get(user=self.user, year=now.year, month=now.month)
        self.assertEqual(ledger.words_used, 100)

    def test_deduct_increments_existing_ledger(self):
        now = timezone.now()
        UsageLedger.objects.create(user=self.user, year=now.year, month=now.month, words_used=200)
        deduct_usage(self.user, 300)
        ledger = UsageLedger.objects.get(user=self.user, year=now.year, month=now.month)
        self.assertEqual(ledger.words_used, 500)


class EnqueueGenerationTests(TestCase):
    def setUp(self):
        self.user = make_user()
        self.project = make_project(self.user)

    @patch("apps.content.tasks.generate_content_task")
    def test_enqueue_creates_generation(self, mock_task):
        mock_task.delay.return_value = MagicMock(id="fake-task-id")
        gen = enqueue_generation(self.user, self.project, "blog_post")
        self.assertEqual(gen.status, "queued")
        self.assertEqual(gen.content_type, "blog_post")
        mock_task.delay.assert_called_once_with(gen.id)

    @patch("apps.content.tasks.generate_content_task")
    def test_enqueue_blocked_when_quota_exceeded(self, mock_task):
        now = timezone.now()
        UsageLedger.objects.create(user=self.user, year=now.year, month=now.month, words_used=5_000)
        with self.assertRaises(ValueError) as ctx:
            enqueue_generation(self.user, self.project, "blog_post")
        self.assertIn("Monthly word limit", str(ctx.exception))
        mock_task.delay.assert_not_called()

    @patch("apps.content.tasks.generate_content_task")
    def test_rate_limit_blocks_rapid_requests(self, mock_task):
        mock_task.delay.return_value = MagicMock(id="t")
        # Create 5 recent generations manually (simulating limit)
        for _ in range(5):
            ContentGeneration.objects.create(
                user=self.user,
                project=self.project,
                content_type="blog_post",
                status="queued",
            )
        with self.assertRaises(ValueError) as ctx:
            enqueue_generation(self.user, self.project, "blog_post")
        self.assertIn("Rate limit", str(ctx.exception))
